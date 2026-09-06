"""Read-only evidence extraction from the exact supported game executable.

Optional local tooling dependencies: capstone and pefile. Never loads the game
image as code or opens a game process. Outputs bounded disassembly windows.
"""
from pathlib import Path
import bisect
import hashlib
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).parent / ".analysis_deps"))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_REG_RIP

path = Path(sys.argv[1])
raw = path.read_bytes()
sha = hashlib.sha256(raw).hexdigest()
assert sha == "782b904a8f7bbdac1f7a18528f1a5c778691e5aa3087c37c351bf6912585175c", sha
pe = pefile.PE(data=raw, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase
md = Cs(CS_ARCH_X86, CS_MODE_64)
md.detail = True
pdata = next(s for s in pe.sections if s.Name.startswith(b".pdata")).get_data()
functions = sorted((b, e) for b, e, _ in struct.iter_unpack("<III", pdata[:len(pdata) // 12 * 12]) if b and e)
begins = [b for b, _ in functions]


def dump(rva, size):
    print(f"\nRVA 0x{rva:x}..0x{rva+size:x}")
    for ins in md.disasm(pe.get_data(rva, size), base + rva):
        notes = []
        for operand in ins.operands:
            if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                target = ins.address + ins.size + operand.mem.disp - base
                data = pe.get_data(target, 180)
                string = data.split(b"\0", 1)[0]
                if len(string) > 2 and all(32 <= x < 127 for x in string):
                    notes.append(repr(string.decode("ascii")))
                elif len(data) >= 4:
                    notes.append(f"RVA0x{target:x} bytes={data[:8].hex()} float32={struct.unpack('<f',data[:4])[0]:.10g}")
        print(f"{ins.address-base:08x} {ins.bytes.hex(' '):<34} {ins.mnemonic:<9} {ins.op_str}" + (" ; " + " | ".join(notes) if notes else ""))


print(f"EXE SHA256 {sha}")
assertion = b"dt >= .2f\0"
offset = raw.find(assertion)
assert offset >= 0, "assertion string missing"
assertion_rva = pe.get_rva_from_offset(offset)
print(f"Assertion {assertion[:-1]!r} at RVA 0x{assertion_rva:x}")
for section in pe.sections:
    if not section.Characteristics & 0x20000000:
        continue
    code = section.get_data()
    for match in re.finditer(b"[\\x48\\x4c]\\x8d[\\x05\\x0d\\x15\\x1d\\x25\\x2d\\x35\\x3d]", code):
        rva = section.VirtualAddress + match.start()
        ins = next(md.disasm(code[match.start():match.start()+15], base + rva), None)
        if ins and any(o.type == X86_OP_MEM and o.mem.base == X86_REG_RIP and
                       ins.address + ins.size + o.mem.disp == base + assertion_rva for o in ins.operands):
            index = bisect.bisect_right(begins, rva) - 1
            b, e = functions[index]
            print(f"Assertion reference RVA 0x{rva:x}, containing function 0x{b:x}..0x{e:x}")
            dump(b, min(e-b, 0x300))

dump(0x15aa00, 0x289)
dump(0x1184d0, 0x48c)
for section in pe.sections:
    if not section.Characteristics & 0x20000000:
        continue
    code = section.get_data()
    for match in re.finditer(b"\\xe8", code):
        pos = match.start()
        if pos + 5 <= len(code) and section.VirtualAddress + pos + 5 + struct.unpack_from("<i", code, pos+1)[0] == 0x2f7850:
            rva = section.VirtualAddress + pos
            index = bisect.bisect_right(begins, rva) - 1
            b, e = functions[index]
            print(f"Direct EmissionMap::Update call RVA 0x{rva:x}, function 0x{b:x}..0x{e:x}")
            dump(b, min(e-b, 0x180))
