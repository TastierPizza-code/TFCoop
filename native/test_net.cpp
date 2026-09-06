// Standalone Windows harness. Including the implementation permits direct tests
// of malformed datagrams without exporting private protocol state from the DLL.
#include "../upstream/tpf2-multiplayer/bridge/src/net.cpp"
#include <cstdlib>
#include <iostream>
#include <vector>

static std::vector<std::string> delivered;
static std::mutex captureMutex;
static void Capture(const char* line)
{
    std::lock_guard<std::mutex> lk(captureMutex);
    delivered.emplace_back(line);
}
static void Check(bool condition, const char* message)
{
    if (!condition) { std::cerr << "FAIL: " << message << '\n'; std::exit(1); }
}

static NetEvent Chunk(uint16_t idx, uint16_t count, const std::string& text)
{
    NetEvent ev{};
    ev.type = 1;
    ev.chunkIdx = idx;
    ev.chunkCount = count;
    Check(text.size() < NET_CHUNK_TEXT, "test chunk size");
    memcpy(ev.text, text.data(), text.size());
    return ev;
}

static void ClearState()
{
    ResetReassembly();
    delivered.clear();
    g_pending.clear();
    g_lastSent.clear();
    g_early.clear();
    while (!g_outQueue.empty()) g_outQueue.pop();
    g_nextSeq = g_expectedSeq = 1;
    g_lastReceivedSeq = g_receivedBits = 0;
    g_peerSession = 0;
    g_retiredPeerSessions.clear();
    g_deliver = Capture;
}

static size_t DeliveredCount()
{
    std::lock_guard<std::mutex> lk(captureMutex);
    return delivered.size();
}

static bool WaitDelivered(size_t count)
{
    const auto deadline = GetTickCount64() + 2000;
    while (GetTickCount64() < deadline) {
        if (DeliveredCount() >= count) return true;
        Sleep(10);
    }
    return false;
}

int main()
{
    ClearState();
    const std::string full(NET_CHUNK_TEXT - 1, 'a');
    Reassemble(Chunk(0, 2, full));
    Check(delivered.empty(), "partial line must not be delivered");
    Reassemble(Chunk(1, 2, "end"));
    Check(delivered.size() == 1 && delivered[0] == full + "end", "complete line preserves exact bytes");

    ClearState();
    Reassemble(Chunk(1, 2, "orphan"));
    Check(delivered.empty() && g_rxAccum.empty(), "orphan tail rejected");
    Reassemble(Chunk(0, 2, full));
    Reassemble(Chunk(1, 3, full));
    Reassemble(Chunk(2, 3, "tail"));
    Check(delivered.empty() && g_rxAccum.empty(), "changed chunk count discards entire line");
    Reassemble(Chunk(0, 3, full));
    Reassemble(Chunk(2, 3, "skipped"));
    Check(delivered.empty() && g_rxAccum.empty(), "missing chunk rejected");
    Reassemble(Chunk(0, 2, "short middle"));
    Reassemble(Chunk(1, 2, "tail"));
    Check(delivered.empty() && g_rxAccum.empty(), "short intermediate chunk rejected");
    Reassemble(Chunk(0, 0, "zero count"));
    Reassemble(Chunk(0, (uint16_t)(MAX_LINE_CHUNKS + 1), full));
    Check(delivered.empty() && g_rxAccum.empty(), "zero and oversized counts rejected");
    NetEvent noNull = Chunk(0, 1, "");
    memset(noNull.text, 'x', sizeof(noNull.text));
    Reassemble(noNull);
    Check(delivered.empty() && g_rxAccum.empty(), "unterminated text rejected");
    for (int i = 0; i < 10000; ++i) Reassemble(Chunk(1, 3, full));
    Check(delivered.empty() && g_rxAccum.empty(), "repeated noninitial chunks cannot grow memory");
    Reassemble(Chunk(0, 1, "recovered"));
    Check(delivered.size() == 1 && delivered[0] == "recovered", "good line recovers after malformed traffic");

    ClearState();
    for (size_t i = 0; i < MAX_LINE_CHUNKS; ++i)
        Reassemble(Chunk((uint16_t)i, (uint16_t)MAX_LINE_CHUNKS, full));
    Check(delivered.size() == 1 && delivered[0].size() == MAX_LINE_BYTES, "maximum line delivered without truncation");

    Packet p{};
    p.h.magic = MAGIC;
    p.h.session = 1;
    p.h.seq = 1;
    p.h.type = 1;
    p.ev = Chunk(0, 1, "event");
    Check(ValidPacket(p, sizeof(p)), "full event datagram accepted");
    Check(!ValidPacket(p, sizeof(Header)), "truncated event rejected");
    Check(!ValidPacket(p, sizeof(p) - 1), "one-byte-short event rejected");
    Check(!ValidPacket(p, sizeof(p) + 1), "oversized event rejected");
    p.h.type = 2;
    Check(!ValidPacket(p, sizeof(p)), "unknown packet type rejected");
    p.h.type = 0;
    Check(ValidPacket(p, sizeof(Header)) && !ValidPacket(p, sizeof(p)), "keepalive exact size enforced");
    p.h.type = 1;
    p.ev.type = 0;
    Check(!ValidPacket(p, sizeof(p)), "invalid nested event type rejected");
    p.ev.type = 1;
    p.h.seq = 0;
    Check(!ValidPacket(p, sizeof(p)), "zero event sequence rejected");

    ClearState();
    g_peerEverSeen = true;
    g_lastRecvMs = GetTickCount64();
    std::string maxLine(MAX_LINE_BYTES, 'b');
    Net_QueueLine(maxLine.c_str());
    Check(g_outQueue.size() == MAX_LINE_CHUNKS, "maximum line uses exact bounded chunk count");
    auto rejected = g_droppedOverflow;
    Net_QueueLine("another line");
    Check(g_outQueue.size() == MAX_LINE_CHUNKS && g_droppedOverflow == rejected + 1,
          "outbound capacity refuses whole line");
    while (!g_outQueue.empty()) { Reassemble(g_outQueue.front()); g_outQueue.pop(); }
    Check(delivered.size() == 1 && delivered[0] == maxLine, "outbound chunks round trip exactly");
    auto oversize = g_droppedOversize;
    maxLine.push_back('x');
    Net_QueueLine(maxLine.c_str());
    Net_QueueLine(nullptr);
    Check(g_outQueue.empty() && g_droppedOversize == oversize + 2, "oversized and null sends rejected");

    ClearState();
    Packet early{};
    early.h.type = 1;
    early.h.seq = 2;
    early.ev = Chunk(1, 2, "finish");
    DeliverInOrder(early);
    Check(delivered.empty(), "early packet waits for gap");
    Packet first = early;
    first.h.seq = 1;
    first.ev = Chunk(0, 2, full);
    DeliverInOrder(first);
    Check(delivered.size() == 1 && delivered[0] == full + "finish", "out of order chunks deliver once in order");
    DeliverInOrder(first);
    DeliverInOrder(early);
    Check(delivered.size() == 1, "duplicates do not replay command");

    ClearState();
    g_session = 100;
    g_pending[1] = first;
    g_lastSent[1] = 0;
    ProcessAck(g_session, 0, 0xFFFFFFFF);
    Check(g_pending.size() == 1, "initial ACK zero never acknowledges first event");
    ProcessAck(g_session - 1, 1, 0);
    Check(g_pending.size() == 1, "previous session ACK cannot discard new first event");
    ProcessAck(g_session, 1, 0);
    Check(g_pending.empty(), "matching session ACK acknowledges received event");

    ClearState();
    Packet keepalive{};
    keepalive.h.magic = MAGIC;
    keepalive.h.session = 200;
    keepalive.h.seq = 3; // both events already sent, first one was lost
    ProcessIncoming(keepalive);
    Check(g_expectedSeq == 1 && g_lastReceivedSeq == 0, "first keepalive cannot imply delivered prefix");
    early.h.session = first.h.session = keepalive.h.session;
    ProcessIncoming(early);
    Check(g_expectedSeq == 1 && delivered.empty(), "second event waits for missing first event after keepalive");
    ProcessIncoming(first);
    Check(delivered.size() == 1 && delivered[0] == full + "finish", "retransmitted first event repairs startup reorder");
    Packet newSession = first;
    newSession.h.session = 201;
    newSession.ev = Chunk(0, 1, "new epoch");
    ProcessIncoming(newSession);
    Check(delivered.size() == 2 && delivered[1] == "new epoch", "new stream starts at first event");
    ProcessIncoming(first);
    ProcessIncoming(keepalive);
    Check(delivered.size() == 2 && g_peerSession == 201, "retired session packets cannot rewind active stream");

    ClearState();
    first.h.session = 300;
    early.h.session = 300;
    ProcessIncoming(early); // first ever datagram is event 2, no keepalive
    Check(g_expectedSeq == 1 && delivered.empty(), "out of order first datagram cannot skip event one");
    ProcessIncoming(first);
    Check(delivered.size() == 1 && delivered[0] == full + "finish", "first datagram reorder recovers exact command");

    g_nextSeq = 88;
    g_pending[87] = first;
    g_outQueue.push(Chunk(0, 1, "old destination"));
    const uint32_t oldSession = g_session;
    Check(Net_SetPeer("127.0.0.1", 34567), "peer update accepted");
    ApplyPeerUpdate();
    Check(g_session != oldSession && g_nextSeq == 1 && g_pending.empty() && g_outQueue.empty(),
          "peer change resets complete sender epoch and backlog");
    Check(g_expectedSeq == 1 && g_peerSession == 0 && !g_peerEverSeen,
          "peer change resets receiver and requires fresh liveness");

    // Headless real localhost UDP integration: the first event is delayed until
    // after a keepalive and event two; a malformed datagram and foreign source
    // must not execute anything or consume the legitimate event's sequence.
    ClearState();
    Check(EnsureWsa(), "Winsock initialized");
    SOCKET peerSocket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    SOCKET foreignSocket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    Check(peerSocket != INVALID_SOCKET && foreignSocket != INVALID_SOCKET, "test peer sockets created");
    sockaddr_in peerAddress{};
    peerAddress.sin_family = AF_INET;
    inet_pton(AF_INET, "127.0.0.1", &peerAddress.sin_addr);
    Check(bind(peerSocket, (sockaddr*)&peerAddress, sizeof(peerAddress)) == 0, "test peer bound");
    int addressLength = sizeof(peerAddress);
    Check(getsockname(peerSocket, (sockaddr*)&peerAddress, &addressLength) == 0, "test peer port known");
    Check(Net_Init(0, "127.0.0.1", ntohs(peerAddress.sin_port), Capture), "real network thread started");
    sockaddr_in destination = peerAddress;
    destination.sin_port = htons(Net_LocalPort());
    auto sendPacket = [&](SOCKET socket, const Packet& packet, int size) {
        Check(sendto(socket, (const char*)&packet, size, 0, (sockaddr*)&destination,
                     sizeof(destination)) == size, "real datagram sent");
    };
    keepalive.h.session = 500;
    sendPacket(peerSocket, keepalive, sizeof(Header));
    first.h.magic = early.h.magic = MAGIC;
    first.h.session = early.h.session = 500;
    sendPacket(peerSocket, early, sizeof(Packet));
    Sleep(100);
    Check(DeliveredCount() == 0, "real early datagrams do not skip the lost first event");
    sendPacket(peerSocket, first, sizeof(Packet));
    Check(WaitDelivered(1), "real delayed first event completes line");
    {
        std::lock_guard<std::mutex> lk(captureMutex);
        Check(delivered[0] == full + "finish", "real UDP exact ordered payload");
    }
    Packet third = first;
    third.h.seq = 3;
    third.ev = Chunk(0, 1, "third");
    sendPacket(foreignSocket, third, sizeof(Packet));
    sendPacket(peerSocket, third, sizeof(Packet) - 1);
    Sleep(100);
    Check(DeliveredCount() == 1, "foreign source and truncated datagram cannot execute event");
    sendPacket(peerSocket, third, sizeof(Packet));
    Check(WaitDelivered(2), "legitimate event still delivered after rejected datagrams");
    sendPacket(peerSocket, first, sizeof(Packet));
    sendPacket(peerSocket, third, sizeof(Packet));
    Sleep(100);
    Check(DeliveredCount() == 2, "real UDP duplicates do not replay");
    closesocket(peerSocket);
    closesocket(foreignSocket);
    Net_Shutdown();
    std::cout << "Native network validation, bounded reassembly and ordering: PASS\n";
    return 0;
}
