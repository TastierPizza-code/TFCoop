; Stand-ins with the exact stolen instruction sequences of build 35924.
; The getter has a relative CALL, exercising relocation in the real patcher.
EXTERN ProbeFakeBody:PROC
EXTERN ProbeFakeLookup:PROC
PUBLIC ProbeFakeFirstReturn
PUBLIC ProbeFakeSecondReturn
.code
ProbeFakeStep PROC
    DB 040h
    push rbx
    push r14
    sub rsp, 68h
    mov rbx, rdx
    mov r14, rcx
    cmp rdx, 3e8h
    mov rcx, r14
    mov rdx, rbx
    call ProbeFakeBody
    add rsp, 68h
    pop r14
    pop rbx
    ret
ProbeFakeStep ENDP
ProbeFakeGetter PROC
    sub rsp, 28h
    lea rdx, [rcx+10h]
    mov rcx, [rcx+8]
    call ProbeFakeLookup
    mov eax, [rax+4]
    add rsp, 28h
    ret
ProbeFakeGetter ENDP
ProbeFakeFirstRead PROC
    sub rsp, 28h
    call ProbeFakeGetter
ProbeFakeFirstReturn LABEL BYTE
    add rsp, 28h
    ret
ProbeFakeFirstRead ENDP
ProbeFakeSecondRead PROC
    sub rsp, 28h
    call ProbeFakeGetter
ProbeFakeSecondReturn LABEL BYTE
    add rsp, 28h
    ret
ProbeFakeSecondRead ENDP
END
