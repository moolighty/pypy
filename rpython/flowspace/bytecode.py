"""
Bytecode handling classes and functions for use by the flow space.
"""
from rpython.tool.stdlib_opcode import host_bytecode_spec
from opcode import EXTENDED_ARG, HAVE_ARGUMENT
import opcode
from rpython.flowspace.argument import Signature

CO_GENERATOR = 0x0020
CO_VARARGS = 0x0004
CO_VARKEYWORDS = 0x0008

def cpython_code_signature(code):
    "([list-of-arg-names], vararg-name-or-None, kwarg-name-or-None)."
    argcount = code.co_argcount
    argnames = list(code.co_varnames[:argcount])
    if code.co_flags & CO_VARARGS:
        varargname = code.co_varnames[argcount]
        argcount += 1
    else:
        varargname = None
    if code.co_flags & CO_VARKEYWORDS:
        kwargname = code.co_varnames[argcount]
        argcount += 1
    else:
        kwargname = None
    return Signature(argnames, varargname, kwargname)


class BytecodeCorruption(Exception):
    pass


class HostCode(object):
    """
    A wrapper around a native code object of the host interpreter
    """
    def __init__(self, argcount, nlocals, stacksize, flags,
                 code, consts, names, varnames, filename,
                 name, firstlineno, lnotab, freevars):
        """Initialize a new code object"""
        assert nlocals >= 0
        self.co_argcount = argcount
        self.co_nlocals = nlocals
        self.co_stacksize = stacksize
        self.co_flags = flags
        self.co_code = code
        self.consts = consts
        self.names = names
        self.co_varnames = varnames
        self.co_freevars = freevars
        self.co_filename = filename
        self.co_name = name
        self.co_firstlineno = firstlineno
        self.co_lnotab = lnotab
        self.signature = cpython_code_signature(self)

    @classmethod
    def _from_code(cls, code):
        """Initialize the code object from a real (CPython) one.
        """
        return cls(code.co_argcount,
                   code.co_nlocals,
                   code.co_stacksize,
                   code.co_flags,
                   code.co_code,
                   list(code.co_consts),
                   list(code.co_names),
                   list(code.co_varnames),
                   code.co_filename,
                   code.co_name,
                   code.co_firstlineno,
                   code.co_lnotab,
                   list(code.co_freevars))

    @property
    def formalargcount(self):
        """Total number of arguments passed into the frame, including *vararg
        and **varkwarg, if they exist."""
        return self.signature.scope_length()

    def read(self, offset):
        """
        Decode the instruction starting at position ``offset``.

        Returns (next_offset, instruction).
        """
        co_code = self.co_code
        opnum = ord(co_code[offset])
        next_offset = offset + 1

        if opnum >= HAVE_ARGUMENT:
            lo = ord(co_code[next_offset])
            hi = ord(co_code[next_offset + 1])
            next_offset += 2
            oparg = (hi * 256) | lo
        else:
            oparg = 0

        while opnum == EXTENDED_ARG:
            opnum = ord(co_code[next_offset])
            if opnum < HAVE_ARGUMENT:
                raise BytecodeCorruption
            lo = ord(co_code[next_offset + 1])
            hi = ord(co_code[next_offset + 2])
            next_offset += 3
            oparg = (oparg * 65536) | (hi * 256) | lo

        if opnum in opcode.hasjrel:
            oparg += next_offset
        elif opnum in opcode.hasname:
            oparg = self.names[oparg]
        try:
            op = BCInstruction.num2op[opnum].decode(oparg, offset, self)
        except KeyError:
            op = BCInstruction(opnum, oparg, offset)
        return next_offset, op

    @property
    def is_generator(self):
        return bool(self.co_flags & CO_GENERATOR)

OPNAMES = host_bytecode_spec.method_names

class BCInstruction(object):
    """
    A bytecode instruction, comprising an opcode and an optional argument.

    """
    num2op = {}

    def __init__(self, opcode, arg, offset=-1):
        self.name = OPNAMES[opcode]
        self.num = opcode
        self.arg = arg
        self.offset = offset

    @classmethod
    def decode(cls, arg, offset, code):
        return cls(arg, offset)

    def eval(self, ctx):
        return getattr(ctx, self.name)(self.arg)

    @classmethod
    def register_name(cls, name, op_class):
        try:
            num = OPNAMES.index(name)
            cls.num2op[num] = op_class
            return num
        except ValueError:
            return -1

    def __repr__(self):
        return "%s(%s)" % (self.name, self.arg)

def register_opcode(cls):
    """Class decorator: register opcode class as real Python opcode"""
    name = cls.__name__
    cls.name = name
    cls.num = BCInstruction.register_name(name, cls)
    return cls

@register_opcode
class LOAD_CONST(BCInstruction):
    def __init__(self, arg, offset=-1):
        self.arg = arg
        self.offset = offset

    @staticmethod
    def decode(arg, offset, code):
        return LOAD_CONST(code.consts[arg], offset)
