"""
Z-Machine Opcode Processor for CircuitPython
Handles Z-machine instruction execution and text processing

This module implements the core Z-machine opcodes needed for
interactive fiction games like Zork.
"""

import sys
import random
import re

# Z-machine instruction types
LONG_FORM = 0
SHORT_FORM = 1
VARIABLE_FORM = 2
EXTENDED_FORM = 3

# Operand types
LARGE_CONSTANT = 0
SMALL_CONSTANT = 1
VARIABLE = 2
OMITTED = 3

# call types
FUNCTION = 0x0000
PROCEDURE = 0x1000
ASYNC = 0x2000

PAGE_SIZE = 0x200
PAGE_MASK = 0x1FF

SYNONYMS_OFFSET = 0x24

v3_lookup_table = [
   "abcdefghijklmnopqrstuvwxyz",
   "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
   " \n0123456789.,!?_#'\"/\\-:()"
]

h_words_offset = 8
h_type = 3

if h_type < 4:
    address_scaler = 2;
    story_shift = 1;
    #property_mask = P3_MAX_PROPERTIES - 1;

    property_offset = 7
    max_properties = 0x20
    property_mask = max_properties - 1
    object_size = 9
    object_attributes = 0
    object_parent = 4
    object_next = 5
    object_child = 6
    object_prop_offset = 7
    property_size_mask = 0xe0;
elif h_type < V8:
    address_scaler = 4;
    story_shift = 2;
    #property_mask = P4_MAX_PROPERTIES - 1;
    property_offset = 12
    max_properties = 0x40
    property_mask = max_properties - 1
    object_size = 14
    object_attributes = 0
    object_parent = 6
    object_next = 8
    object_child = 10
    object_prop_offset = 12
    property_size_mask = 0x3f;
else:
    address_scaler = 8;
    story_shift = 3;
    #property_mask = P4_MAX_PROPERTIES - 1;
    property_offset = 12
    max_properties = 0x40
    object_size = 14
    property_size_mask = 0x3f;

class Frame:
    def __init__(self):
        self.return_pointer = 0 # Program counter
        self.variable = 0 # Stack variable
        self.result_var = 0
        self.ctype = FUNCTION
        self.arg_count = 0 # for +V5 versions
        self.count = 0
        self.local_vars = [0]*15
        self.data_stack = []

class ZProcessor:
    def __init__(self, zmachine):
        self.zm = zmachine
        self.instruction_count = 0
        # Opcode dispatch table (simplified set for basic functionality)
        self.opcodes = {
            # 0OP opcodes
            0x30: [self.op_rtrue,"op_rtrue"],      # rtrue
            0x31: [self.op_rfalse,"op_rfalse"],     # rfalse
            0x32: [self.op_print,"op_print"],      # print
            0x33: [self.op_print_ret,"op_print_ret"],  # print_ret
            0x38: [self.op_ret_popped,"op_ret_popped"], # ret_popped
            0x39: [self.op_catch,"op_catch"],      # catch
            0x3A: [self.op_quit,"op_quit"],       # quit
            0x3B: [self.op_new_line,"op_new_line"],   # new_line

            # 1OP opcodes
            0x80: [self.op_jz,"op_jz"],         # jz
            0x81: [self.op_get_sibling,"op_get_sibling"], # get_sibling
            0x82: [self.op_get_child,"op_get_child"],  # get_child
            0x83: [self.op_get_parent,"op_get_parent"], # get_parent
            0x84: [self.op_get_prop_len,"op_get_prop_len"], # get_prop_len
            0x85: [self.op_inc,"op_inc"],        # inc
            0x86: [self.op_dec,"op_dec"],        # dec
            0x87: [self.op_print_addr,"op_print_addr"], # print_addr
            0x8A: [self.op_print_obj,"op_print_obj"], # print_obj
            0x8B: [self.op_ret,"op_ret"],        # ret
            0x8C: [self.op_jump,"op_jump"],       # jump
            0x8D: [self.op_print_paddr,"op_print_paddr"], # print_paddr
            0x8E: [self.op_load,"op_load"],       # load
            0x8F: [self.op_not,"op_not"],        # not (or call_1n in v4+)

            # 2OP opcodes
            0x01: [self.op_je,"op_je"],         # je
            0x02: [self.op_jl,"op_jl"],         # jl
            0x03: [self.op_jg,"op_jg"],         # jg
            0x04: [self.op_dec_chk,"op_dec_chk"],   # dec_chk
            0x05: [self.op_inc_chk,"op_inc_chk"],    # inc_chk
            0x06: [self.op_jin,"op_jin"],        # jin
            0x07: [self.op_test,"op_test"],       # test
            0x08: [self.op_or,"op_or"],         # or
            0x09: [self.op_and,"op_and"],        # and
            0x0A: [self.op_test_attr,"op_test_attr"],  # test_attr
            0x0B: [self.op_set_attr,"op_set_attr"],   # set_attr
            0x0C: [self.op_clear_attr,"op_clear_attr"], # clear_attr
            0x0D: [self.op_store,"op_store"],      # store
            0x0E: [self.op_insert_obj,"op_insert_obj"], # insert_obj
            0x0F: [self.op_loadw,"op_loadw"],      # loadw
            0x10: [self.op_loadb,"op_loadb"],      # loadb
            0x11: [self.op_get_prop,"op_get_prop"],   # get_prop
            0x12: [self.op_get_prop_addr,"op_get_prop_addr"], # get_prop_addr
            0x13: [self.op_get_next_prop,"op_get_next_prop"], # get_next_prop
            0x14: [self.op_add,"op_add"],        # add
            0x15: [self.op_sub,"op_sub"],        # sub
            0x16: [self.op_mul,"op_mul"],        # mul
            0x17: [self.op_div,"op_div"],        # div
            0x18: [self.op_mod,"op_mod"],        # mod
            0x19: [self.op_call_2s,"op_call_2s"],# call 2s

            # VAR opcodes
            0x20: [self.op_call,"op_call"],       # call (call_vs in v4+)
            0x21: [self.op_storew,"op_storew"],     # storew
            0x22: [self.op_storeb,"op_storeb"],     # storeb
            0x23: [self.op_put_prop,"op_put_prop"],   # put_prop
            0x24: [self.op_sread,"op_sread"],      # sread (aread in v4+)
            0x25: [self.op_print_char,"op_print_char"], # print_char
            0x26: [self.op_print_num,"op_print_num"],  # print_num
            0x27: [self.op_random,"op_random"],     # random
            0x28: [self.op_push,"op_push"],       # push
            0x29: [self.op_pull,"op_pull"],       # pull
        }

    def fetch_instruction(self):
        """Fetch and decode the next instruction"""
        debug_count = 999999
        #debug_count = 0 # use this to enable debugging at start
        if self.instruction_count >= debug_count:
            self.zm.debug = 2 # turn on debugging output
        pccount = self.zm.pc
        if self.zm.pc >= len(self.zm.memory):
            raise RuntimeError("PC out of bounds")

        opcode_byte = self.zm.read_byte(self.zm.pc)
        self.zm.pc += 1
        self.zm.print_debug(3,f"opcode_byte: 0x{opcode_byte:02x}")

        # Determine instruction form
        if opcode_byte >= 0xC0:
            # Variable form: VAR
            form = VARIABLE_FORM
            opcode = opcode_byte & 0x1F
            self.zm.print_debug(3,f"opcode_byte/opcode = 0x{opcode_byte:02x}/0x{opcode:02x}")
            operand_types = self.decode_operand_types()
            operand_count = len([t for t in operand_types if t != OMITTED])
            self.zm.print_debug(3,f"operand count:{operand_count}, types:{operand_types}")
        elif opcode_byte >= 0xB0:
            # short form: 0OP
            form = SHORT_FORM
            opcode = opcode_byte & 0x3F
            operand_count = 0
            operand_types = []
        elif opcode_byte >= 0x80:
            # Short form: 1OP
            form = SHORT_FORM
            opcode = opcode_byte & 0x0F
            operand_type = (opcode_byte & 0x30) >> 4
            self.zm.print_debug(3,f"1opcode = {opcode}")
            operand_count = 1
            operand_types = [operand_type]
        else:
            # Long form: 2OP
            form = LONG_FORM
            opcode = opcode_byte & 0x1F
            self.zm.print_debug(3,f"2opcode byte = {opcode}")
            operand_count = 2
            operand_types = [
                SMALL_CONSTANT if (opcode_byte & 0x40) == 0 else VARIABLE,
                SMALL_CONSTANT if (opcode_byte & 0x20) == 0 else VARIABLE
            ]

        # Fetch operands
        operands = []

        for op_type in operand_types:
            if op_type == OMITTED:
                break
            elif op_type == LARGE_CONSTANT:
                value = self.zm.read_word(self.zm.pc)
                self.zm.print_debug(3,f"fetch instruction: read large constant: pc=0x{self.zm.pc:02X}, value={value}")
                self.zm.pc += 2
                operands.append(value)
            elif op_type == SMALL_CONSTANT:
                value = self.zm.read_byte(self.zm.pc)
                self.zm.print_debug(3,f"fetch instruction: read small constant: pc=0x{self.zm.pc:02X}, value={value}")
                self.zm.pc += 1
                operands.append(value)
            elif op_type == VARIABLE:
                var_num = self.zm.read_byte(self.zm.pc)
                self.zm.print_debug(3,f"fetch instruction: read variable: pc=0x{self.zm.pc:02X}, var_num={var_num}")
                self.zm.pc += 1
                #if var_num <= 15:
                #    self.print_frame(self.zm.call_stack[-1],"fetch_instruction")
                operands.append(self.read_variable(var_num))
        pccount = self.zm.pc - pccount
        return opcode, operands, form, pccount, opcode_byte

    def decode_operand_types(self):
        """Decode operand types for variable form instructions"""
        types_byte = self.zm.read_byte(self.zm.pc)
        self.zm.pc += 1

        types = []
        for i in range(4):
            op_type = (types_byte >> (6 - 2*i)) & 3
            types.append(op_type)
            if op_type == OMITTED:
                break

        return types

    def print_frame(self, frame, i = "0"):
        pass
        self.zm.print_debug(3,f"## frame {i} ##")
        self.zm.print_debug(3,f"# return_pointer: 0x{frame.return_pointer:02X}")
        self.zm.print_debug(3,f"# result_var: {frame.result_var}")
        self.zm.print_debug(3,f"# variable: {frame.variable}")
        self.zm.print_debug(3,f"# local var count: {frame.count}")
        self.zm.print_debug(3,f"# local_vars: {frame.local_vars}")
        self.zm.print_debug(3,f"# data stack: {frame.data_stack}")
        self.zm.print_debug(3,"## end ##")

    def print_frame_stack(self):
            self.zm.print_debug(3,"### frame stack top ###")
            #for i in range(len(self.zm.call_stack)):
            for i in range(len(self.zm.call_stack), 0, -1):
                self.print_frame(self.zm.call_stack[i-1],i)
            self.zm.print_debug(3,"### frame stack bottom ###")

    def read_variable(self, var_num):
        """Read value from variable"""
        if var_num == 0:
            # Stack variable
            if(len(self.zm.call_stack[-1].data_stack) > 0):
                value = self.zm.call_stack[-1].data_stack.pop()
                self.zm.print_debug(3,f"read data stack value {value}")
                self.zm.print_debug(3,f"data stack({len(self.zm.call_stack[-1].data_stack)}): {self.zm.call_stack[-1].data_stack}")
                return value
            else:
                #self.zm.print_debug(3,"warning: data stack is empty")
                self.zm.print_error("data stack is empty in read_variable()")
                self.zm.game_running = False
                return 0
        elif var_num <= 15:
            # Local variable
            f = self.zm.call_stack[-1]
            #if hasattr(f,"local_vars"):
            self.zm.print_debug(3,f"read local var {var_num - 1}: {f.local_vars[var_num - 1]} {f.local_vars}")
            return f.local_vars[var_num - 1]
            return 0
        else:
            # Global variable
            global_index = var_num - 16
            addr = self.zm.variables_addr+global_index*2
            #print(f"debug: index:{global_index}, var mem start: 0x{self.zm.variables_addr:04X}, address: 0x{addr:04X}")
            #value = self.zm.memory[addr] << 8 | self.zm.memory[addr+1]
            value = self.zm.read_word(addr)
            self.zm.print_debug(3,f"read global var {global_index} from 0x{addr:04x}: {value}")
            return value

    def write_variable(self, var_num, value):
        """Write value to variable"""
        self.zm.print_debug(3,f"write_variable() {var_num} {value}")
        value = value & 0xFFFF  # Ensure 16-bit value

        if var_num == 0:
            # Stack variable
            self.zm.call_stack[-1].data_stack.append(value)
            self.zm.print_debug(3,f"write data stack value {value}")
            self.zm.print_debug(3,f"data stack({len(self.zm.call_stack[-1].data_stack)}): {self.zm.call_stack[-1].data_stack}")
        elif var_num <= 15:
            # Local variable
            f = self.zm.call_stack[-1]
            if hasattr(f,"local_vars"):
                f.local_vars[var_num -1 ] = value
                self.zm.print_debug(3,f"write local var {var_num - 1}: {value} {f.local_vars}")
        else:
            # Global variable
            global_index = var_num - 16
            addr = self.zm.variables_addr + global_index*2
            self.zm.print_debug(3,f"index:{global_index}, var mem start: 0x{self.zm.variables_addr:04X}, address: 0x{addr:04X}")
            self.zm.write_word(addr, value)
            self.zm.print_debug(3,f"write global var {global_index} to 0x{addr:04x}: {value}")

    def init_frame(self):
        f = Frame()
        f.return_pointer = self.zm.read_word(0x06)  # Initial PC
        #print("debug: ptr: ", f.return_pointer)
        #print(f"debug 2: 0x{self.zm.memory[0x06]:02x}")
        self.zm.call_stack.append(f)
        #print(f"debug: initial frame {len(self.zm.call_stack)}:")
        #self.print_frame(f,0)

    def execute_instruction(self):
        """Execute one Z-machine instruction"""

        try:
            opcode, operands, form, pccount, opcode_byte = self.fetch_instruction()
            self.instruction_count += 1
            maxcount = 3000
            if self.instruction_count > maxcount:
                self.zm.print_error(f"{maxcount} instruction limit reached")
                sys.exit()

            # Map opcode based on form
            if form == LONG_FORM:
                full_opcode = opcode  # 2OP opcodes
            elif form == SHORT_FORM:
                if len(operands) == 0:
                    full_opcode = opcode  # 0OP opcodes
                else:
                    full_opcode = 0x80 | opcode  # 1OP opcodes
            else:  # VARIABLE_FORM
                if opcode_byte & 0x20 == 0:
                    full_opcode = opcode # 2OP opcodes
                else:
                    full_opcode = 0x20 | opcode  # VAR opcodes
                #print(f"opcode_byte:0x{opcode_byte:02x} opcode:0x{opcode:02x} full_opcode:0x{full_opcode:02x}")
            self.zm.opcode = full_opcode
            # Execute opcode
            if full_opcode in self.opcodes:
                self.zm.print_debug(1,f"**start {self.instruction_count}:{self.opcodes[full_opcode][1]} {operands} pc:0x{(self.zm.pc-pccount):04x}/0x{self.zm.pc:04x} opcode:0x{opcode_byte:02X}/0x{opcode:02X}/0x{full_opcode:02X}")
                self.opcodes[full_opcode][0](operands)
                self.zm.print_debug(2,f"local vars: {self.zm.call_stack[-1].local_vars}")
                self.zm.print_debug(2,f"data stack: {self.zm.call_stack[-1].data_stack}")

                self.zm.print_debug(3,f"**end {self.opcodes[full_opcode][1]} pc:0x{(self.zm.pc):04X}")
            else:
                self.zm.print_error(f"Unimplemented opcode:0x{opcode:02X}/0x{full_opcode:02X} pc:0x{(self.zm.pc-pccount):04X}")
                sys.exit()

        except Exception as e:
            self.zm.print_error(f"Execution error at PC 0x{self.zm.pc:04X}: {e}")
            self.zm.game_running = False

    """
     Notes from c source code:
     Take a jump after an instruction based on the flag, either true or false. The
     jump can be modified by the change logic flag. Normally jumps are taken
     when the flag is true. When the change logic flag is set then the jump is
     taken when flag is false. A PC relative jump can also be taken. This jump can
     either be a positive or negative byte or word range jump. An additional
     feature is the return option. If the jump offset is zero or one then that
     literal value is passed to the return instruction, instead of a jump being
     taken. Complicated or what!
    """
    def branch(self, condition):
        """Handle conditional branch"""
        self.zm.print_debug(3,f"branch() {condition}")
        self.zm.print_debug(3,f"pc = 0x{self.zm.pc:02X}")

        branch_byte = self.zm.read_byte(self.zm.pc)
        self.zm.pc = self.zm.pc + 1
        self.zm.print_debug(3,f"branch_byte 1:0x{branch_byte:02X}")

        branch_on_true = condition
        if (branch_byte & 0x80) == 0:
            branch_on_true = not branch_on_true
        branch_offset = branch_byte & 0x3F
        self.zm.print_debug(3,"branch_on_true: {branch_on_true}")
        self.zm.print_debug(3,f"pc = 0x{self.zm.pc:02X}")
        if (branch_byte & 0x40) == 0:
            # Two-byte offset
            second_byte = self.zm.read_byte(self.zm.pc)
            self.zm.pc += 1
            self.zm.print_debug(3,f"branch_byte 2:0x{second_byte:02X}")
            branch_offset = ((branch_offset << 8) | second_byte)
            if branch_offset & 0x2000:
                branch_offset |= 0xC000  # Sign extend
            if branch_offset > 0 and branch_offset & 0x8000 :
                branch_offset -= 0x10000 # make negative
            self.zm.print_debug(3,f"branch_offset=0x{branch_offset:0X}")
        if branch_on_true == True:
            self.zm.print_debug(3,f"branch_on_true: {branch_on_true}")
            self.zm.print_debug(3,f"branch offset is 0x{branch_offset:04X}")
            if branch_offset == 0:
                self.op_rfalse([])
            elif branch_offset == 1:
                self.op_rtrue([])
            else:
                self.zm.pc += branch_offset - 2
        self.zm.print_debug(3,f"return branch(), branch_offset = 0x{branch_offset:04X}, pc = 0x{self.zm.pc:04X}")

    def print_object(self, obj):
        objp = self.get_object_address(obj)
        self.zm.print_debug(3,f"~~Object {obj}(0x{objp:04x}):")
        self.zm.print_debug(3,f"~parent: {self.zm.read_byte(objp + object_parent)}")
        self.zm.print_debug(3,f"~next: {self.zm.read_byte(objp + object_next)}")
        self.zm.print_debug(3,f"~child: {self.zm.read_byte(objp + object_child)}")

    def read_object(self, objp, field):
        self.zm.print_debug(3,f"read_object() {objp} {field}")
        if field == object_parent:
            result = self.zm.read_byte(objp + object_parent)
        elif field == object_next:
            result = self.zm.read_byte(objp + object_next)
        else:
            result = self.zm.read_byte(objp + object_child)
        self.zm.print_debug(3,f"read_object() returns {result}")
        return result

    def write_object(self, objp, field, value):
        self.zm.print_debug(3,f"write_obj() {objp} {field} {value}")

        if field == object_parent:
            self.zm.write_byte(objp + object_parent, value)
        elif field == object_next:
            self.zm.write_byte(objp + object_next, value)
        else:
            self.zm.write_byte(objp + object_child, value)
        self.zm.print_debug(3,"write_obj() done")

    """
    Remove an object by unlinking from the its parent object and from its
    siblings.
    """
    def remove_object(self, obj):
        self.zm.print_debug(3,f"remove_object() {obj}")
        objp = self.get_object_address(obj)

        # Get parent of object, and return if no parent
        parent = self.read_object( objp, object_parent)

        self.zm.print_debug(3,f"parent: {parent}")
        if parent == 0:
            return
        # Get address of parent object

        parentp = self.get_object_address( parent)
        # Find first child of parent
        child = self.read_object( parentp, object_child)
        # If object is first child then just make the parent child pointer
        # equal to the next child
        if child == obj:
            self.write_object( parentp, object_child, self.read_object( objp, object_next ) )
        else:
            # Walk down the child chain looking for this object
            while True:
                childp = self.get_object_address(child)
                child = self.read_object(childp, object_next)

                if child == obj:
                    break
            # Set the next pointer the previous child to the next pointer
            # of the current object child pointer */

            self.write_object( childp, object_next, self.read_object( objp, object_next ) )

        # Set the parent and next child pointers to NULL
        self.write_object( objp, object_parent, 0 )
        self.write_object( objp, object_next, 0 )
        self.zm.print_debug(3,"remove_object() done")

    def get_property_addr(self, obj):
        """Calculate the address of the start of the property list associated with an object."""
        self.zm.print_debug(3,f"get_property_addr() {obj}")
        object_addr = self.get_object_address(obj)+ property_offset
        prop_addr = self.zm.read_word( object_addr)
        size = self.zm.read_byte( prop_addr )
        self.zm.print_debug(3,f"object: {obj} object_addr: {object_addr} prop_addr: {prop_addr} size: {size}")
        value = prop_addr + ( size * 2 ) + 1
        self.zm.print_debug(3,f"get_property_addr() returns {value}")
        return value

    def get_next_prop(self, prop_addr):
        """Calculate the address of the next property in a property list."""
        self.zm.print_debug(3,f"get_next_prop() {prop_addr}")
        value = self.zm.read_byte( prop_addr )
        prop_addr+=1

        """Calculate the length of this property"""

        if h_type <= 3:
            value >>= 5;
        elif not( value & 0x80 ):
            value >>= 6;
        else:
            value = self.get_byte( prop_addr )
            value &= property_size_mask;
            if value == 0:
                value = 64  #spec 1.0

        """Address property length to current property pointer"""
        return prop_addr + value + 1;

    # Opcode implementations (simplified)
    def op_rtrue(self, operands):
        """Return true from current routine"""
        self.return_from_routine(1)

    def op_rfalse(self, operands):
        """Return false from current routine"""
        self.return_from_routine(0)

    def op_print(self,operands):
        """Print literal string"""
        text = self.decode_string(self.zm.pc)
        self.zm.print_text(text)
        self.zm.print_debug(3,f"op_string: '{text}'")
        # Skip over the string
        self.zm.pc = self.skip_string(self.zm.pc)

    def op_print_ret(self, operands):
        """Print literal string and return true"""
        self.op_print(operands)
        self.zm.print_text("\n")
        self.op_rtrue(operands)

    def op_ret_popped(self, operands):
        """Return popped value from stack"""
        if len(self.zm.call_stack[-1].data_stack) > 0:
            value = self.zm.call_stack[-1].data_stack.pop()
        else:
            value = 0
        self.return_from_routine(value)

    def op_quit(self, operands):
        """Quit the game"""
        self.zm.game_running = False

    def op_new_line(self, operands):
        """Print newline"""
        self.zm.print_text("\n")

    def op_jz(self, operands):
        #self.print_frame(self.zm.call_stack[-1],"op_jz")
        """Jump if zero"""
        if operands:
            self.branch(not operands[0] )

    def op_je(self, operands):
        """Jump if equal"""
        if len(operands) >= 2:
            condition = operands[0] == operands[1]
            # Check additional operands
            for i in range(2, len(operands)):
                if operands[0] == operands[i]:
                    condition = True
                    break
            self.branch(condition)

    def op_jl(self, operands):
        """Jump if less than"""
        if len(operands) >= 2:
            # Convert to signed 16-bit
            a = operands[0] if operands[0] < 32768 else operands[0] - 65536
            b = operands[1] if operands[1] < 32768 else operands[1] - 65536
            self.branch(a < b)

    def op_jg(self, operands):
        """Jump if greater than"""
        if len(operands) >= 2:
            # Convert to signed 16-bit
            a = operands[0] if operands[0] < 32768 else operands[0] - 65536
            b = operands[1] if operands[1] < 32768 else operands[1] - 65536
            self.branch(a > b)

    def op_load(self, operands):
        """Load variable"""
        if operands:
            value = self.read_variable(operands[0])
            # Store result (this is a simplification)
            self.store_result(value)

    def op_store(self, operands):
        """Store value in variable"""
        if len(operands) >= 2:
            self.write_variable(operands[0], operands[1])

    def op_add(self, operands):
        """Add two values"""
        if len(operands) >= 2:
            result = (operands[0] + operands[1]) % 0x10000
            self.store_result(result)

    def op_sub(self, operands):
        """Subtract two values"""
        if len(operands) >= 2:
            result = (operands[0] - operands[1]) % 0x10000
            self.store_result(result)

    def op_print_char(self, operands):
        """Print character"""
        if operands:
            char = chr(operands[0]) if 32 <= operands[0] <= 126 else '?'
            self.zm.print_text(char)

    def op_print_num(self, operands):
        """Print number"""
        if operands:
            # Convert to signed
            num = operands[0] if operands[0] < 32768 else operands[0] - 65536
            self.zm.print_text(str(num))

    # Format and output the status line for type 3 games only.
    def show_status(self):
        # more work is needed, just show location name for now
        if self.read_variable(16) != 0 :
            self.op_print_obj([self.read_variable( 16 )])

    """
    Search the dictionary for a word. Just encode the word and binary chop the
    dictionary looking for it.
    """
    def find_word(self,token, chop, entry_size ):
        self.zm.print_debug(3,f"find_word() {token}")
        buff = []*3
        word_index = 0
        offset = 0
        status = 0

        # Don't look up the word if there are no dictionary entries
        if self.zm.dictionary_size == 0:
            return 0

        # Encode target word */
        buff = self.encode_string( len(token), token);

        """
        Do a binary chop search on the main dictionary, otherwise do
        a linear search
        """
        word_index = chop - 1
        if self.zm.dictionary_size > 0:
            # binary chop until word is found
            while chop > 0:
                chop = int(chop / 2)
                # Calculate dictionary offset
                if word_index > (self.zm.dictionary_size -1):
                    word_index = self.zm.dictionary_size -1
                offset = self.zm.dictionary_offset + ( word_index * entry_size )
                #print(f"debug: index: {word_index}/{chop} compare: 0x{buff[0]:04x} with 0x{self.zm.read_word(offset + 0):04x}, offset: {offset}")
                status1 = buff[0] - self.zm.read_word(offset + 0)
                status2 = buff[1] - self.zm.read_word(offset + 2)
                status3 = buff[2] - self.zm.read_word(offset + 4)
                status = status1
                # if word matches then return dictionary offset
                if status1 == 0 and status2 == 0 and (h_type < 4 or status3 == 0):
                    self.zm.print_debug(3,f"'{token}' found at offset {offset}")
                    return offset
                if status > 0:
                    word_index += chop

                    # deal with end of dictionary case
                    if word_index >= self.zm.dictionary_size:
                        word_index = self.zm.dictionary_size - 1
                else:
                    word_index -= chop
                    # Deal with start of dictionary case
                    if word_index < 0:
                        word_index = 0

        else:
            for word_index in range(0, -self.zm.dictionary_size, 1):
                # calculate dictionary offset
                offset = self.zm.dictionary_offset + (word_index * entry_size)
                # if word matches then return dictionary offset
                status1 = buff[0] - self.zm.read_word(offset + 0)
                status2 = buff[1] - self.zm.read_word(offset + 2)
                status3 = buff[2] - self.zm.read_word(offset + 4)
                if status1 == 0 and status2 == 0 and (h_type < 4 or status3 == 0):
                    self.zm.print_debug(3,f"'{token}' found at offset {offset}")
                    return offset

        self.zm.print_debug(3,"'{token}' not found")
        return 0

    """
    Convert a typed input line into tokens. The token buffer needs some
    additional explanation. The first byte is the maximum number of tokens
    allowed. The second byte is set to the actual number of token read. Each
    token is composed of 3 fields. The first (word) field contains the word
    offset in the dictionary, the second (byte) field contains the token length,
    and the third (byte) field contains the start offset of the token in the
    character buffer.
    """
    def tokenize_line(self,char_buf, token_buf, dictionary, flag):
        self.zm.print_debug(3,f"tokenize line() char_buf:{char_buf} token_buf:{token_buf} dictionary:0x{dictionary:04x} flag:0x{flag:02x}")
        if h_type > 4:
            slen = self.zm.read_byte(char_buf + 1)
            str_end = char_buf + 2 + slen
        else:
            slen = 0
            while self.zm.read_byte(char_buf + slen) != 0:
                slen += 1
            str_end = char_buf + 1 + slen;

        # Initialise word count and pointers
        words = 0
        if h_type > 4:
            cp = char_buf + 2
        else:
            cp = char_buf + 1

        tp = token_buf + 2;

        buff = ""
        for i in range(slen):
            buff += chr(self.zm.read_byte(char_buf + i))
        # Initialise dictionary
        dictp = self.zm.read_word(dictionary)
        count = self.zm.read_byte(dictp)
        dictp += 1
        self.zm.print_debug(3,f"dictp:0x{dictp:04x} count:{count}")

        delims = ""
        punctuation = [0] * 16
        for i in range(count):
            #punctuation[i] = self.zm.read_byte(dictp)
            delims += chr(self.zm.read_byte(dictp))
            dictp += 1
        entry_size = self.zm.read_byte(dictp)
        dictp += 1
        self.zm.dictionary_size = self.zm.read_word(dictp)
        self.zm.dictionary_offset = dictp + 2
        self.zm.print_debug(3,f"dict size: {self.zm.dictionary_size} offset: {self.zm.dictionary_offset}")
        delims = "[" + delims + " \t\n\r\f.,?" + "]"
        # Calculate the binary chop start position
        if self.zm.dictionary_size > 0:
            word_index = self.zm.dictionary_size / 2
            chop = 1
            while True:
                chop *= 2
                word_index = int(word_index / 2)
                if word_index == 0:
                    break
        max_tokens = self.zm.read_byte(token_buf)
        regex = re.compile(delims)
        tokens = regex.split(buff)
        words = 0
        self.zm.print_debug(3,f"buff: '{buff}' to tokens: {tokens}")
        for token in tokens:
            # Get the word offset from the dictionary
            word = self.find_word(token, chop, entry_size)
            if words <= max_tokens: # and word != 0:
                self.zm.write_byte(2+token_buf + words*4 + 0, word >> 8)
                self.zm.write_byte(2+token_buf + words*4 + 1, word & 0xff)
                self.zm.write_byte(2+token_buf + words*4 + 2, len(token))
                self.zm.write_byte(2+token_buf + words*4 + 3, buff.find(token))
                words += 1
        self.zm.write_byte(token_buf,59)
        self.zm.write_byte(token_buf+1,words)

        #print("token buffer:[ ",end="")
        #for i in range(2+words*4):
        #    print(f"{self.zm.read_byte(token_buf + i):02x} ",end="")
        #print("]")
        #print("buff:",buff)

    def op_sread(self, operands):
        """Read string from user"""
        self.zm.print_debug(3,f"op_sread() {operands}")
        if len(operands) >= 2:
            text_buffer = operands[0]
            parse_buffer = operands[1] if len(operands) > 1 else 0

            # Refresh status line
            if h_type < 4:
                self.show_status()

            # Reset line count
            self.zm.lines_written = 0

            # Initialise character pointer and initial read size

            #cbuf = ( char * ) &datap[argv[0]]
            #in_size = ( h_type > 4 ) ? cbuf[1] : 0;
            cbuf = operands[0]
            if h_type > 4:
                in_size = self.zm.read_byte(cbuf + 1)
            else:
                in_size = 0

            # Get user input
            user_input = self.zm.get_input()
            self.instruction_count = 1 # reset for each input

            # turn on debug mode if input start with "~"
            self.zm.debug = 0
            while len(user_input) > 0 and user_input[0] == "~":
                user_input = user_input[1:]
                self.zm.debug += 1 if self.zm.debug <= 10 else 0

            # Store in text buffer
            max_len = self.zm.read_byte(text_buffer)

            # convert string to lowercase
            # user_input = user_input.lower()
            for i in range(max_len):
                if i < len(user_input):
                    self.zm.write_byte(cbuf+i, ord(user_input[i]))
                else:
                    self.zm.write_byte(cbuf+i,0)
            # Tokenize the line, if a token buffer is present */

            if operands[1]:
                self.tokenize_line( text_buffer, operands[1], h_words_offset, 0 )

    def store_result(self, value):
        """Store result of instruction"""
        result_var = self.zm.read_byte(self.zm.pc)
        self.zm.pc += 1
        self.zm.print_debug(3,f"store_result(): write_variable({result_var}, {value})")
        self.write_variable(result_var, value)

    def return_from_routine(self, value):
        """Return from current routine"""

        if self.zm.call_stack:
            #self.zm.pc = self.zm.call_stack[-1].get('stack', []).pop() if self.zm.call_stack[-1].get('stack') else 0
            # get operand count
            self.zm.print_debug(3,f"pop frame {len(self.zm.call_stack)}:")
            #self.print_frame_stack()
            #self.zm.call_stack.pop()
            f = self.zm.call_stack.pop()
            self.print_frame_stack()
            #self.print_frame(f,len(self.zm.call_stack))
            if len(self.zm.call_stack) == 0:
                self.zm.print_error("call stack is empty")
                self.zm.game_running = False
                return

            # restore pc
            newpc = f.return_pointer
            self.zm.print_debug(3,f"pointer from 0x{self.zm.pc:04X} to 0x{newpc:04X}")
            self.zm.pc = newpc
        else:
            self.zm.game_running = False
        # save return value
        # future: check if returning from function call in later ZM versions
        self.store_result(value)

    def write_zchar(self, c):
        c = c & 0xff
        if " " <= c and c <= "~":
            print(c)
        elif c == 13:
            print("\r")
        # don't care about other characters at this time

    def encode_string(self, len, s):
        # Encode Z-machine string
        self.zm.print_debug(3,f"encode_string() '{s}', len:{len}")
        codes = [0]*9
        buffer = [0]*3

        # Initialise codes count and prev_table number
        codes_count = 0
        prev_table = 0

        pos = 0
        while len > 0:
            len -= 1

            """
            Set the table and code to be the ASCII character inducer, then
            look for the character in the three lookup tables. If the
            character isn't found then it will be an ASCII character.
            """
            table = 2
            code = 0

            for i in range(3):
                for j in range(26):
                    if v3_lookup_table[i][j] == s[pos]:
                        table = i
                        code = j

            """
            Type 1 and 2 games differ on how the shift keys are used. Switch
            now depending on the game version.
            """
            if h_type < 3:

                """
                If the current table is the same as the previous table then
                just store the character code, otherwise switch tables.
                """
                if table != prev_table:

                    #Find the table for the next character
                    next_table = 0
                    if len > 0:
                        next_table = 2
                        for i in range(3):
                            for j in range(26):
                                if v3_lookup_table[i][j] == s[pos+1]:
                                    next_table = i

                    """
                    Calculate the shift key. This magic. See the description in
                    decode_text for more information on version 1 and 2 shift
                    key changes.
                    """
                    shift_state = ( table + ( prev_table * 2 ) ) % 3

                    #Only store the shift key if there is a change in table */

                    if shift_state != 0:

                        """
                        If the next character as the uses the same table as
                        this character then change the shift from a single
                        shift to a shift lock. Also remember the current
                        table for the next iteration.
                        """
                        if next_table == table:
                            shift_state += 2
                            prev_table = table
                        else:
                            prev_table = 0

                        # Store the code in the codes buffer
                        if codes_count < 9:
                            codes[codes_count] = shift_state + 1
                            codes_count += 1

            else:

                """
                For V3 games each uppercase or punctuation table is preceded
                by a separate shift key. If this is such a shift key then
                put it in the codes buffer.
                """
                if table != 0 and codes_count < 9:
                    codes[codes_count] = table + 3
                    codes_count += 1
            # Put the character code in the code buffer
            if codes_count < 9:
                codes[codes_count] = code + 6
                codes_count += 1

            """
            Cannot find character in table so treat it as a literal ASCII
            code. The ASCII code inducer (code 0 in table 2) is followed by
            the high 3 bits of the ASCII character followed by the low 5
            bits to make 8 bits in total.
            """
            if table == 2 and code == 0:
                if codes_count < 9:
                    codes[codes_count] = s[pos] >> 5 & 0x07
                    codes_count += 1
                if codes_count < 9:
                    codes[codes_count] = s[pos] & 0x1f
            # Advance to next character
            pos += 1

        # Pad out codes with shift 5's
        for i in range(codes_count,9):
            codes[i] = 5
        #print("debug:",codes)
        # Pack codes into buffer
        buffer[0] = codes[0] << 10 | codes[1] << 5 | codes[2]
        buffer[1] = codes[3] << 10 | codes[4] << 5 | codes[5]
        buffer[2] = codes[6] << 10 | codes[7] << 5 | codes[8]

        # Terminate buffer at 6 or 9 codes depending on the version
        if h_type < 4:
            buffer[1] |= 0x8000
        else:
            buffer[2] |= 0x8000
        return buffer

    def decode_string(self, addr):
        """Decode Z-machine string"""
        #print(f"debug: decode_string(addr=0x{addr:04x})")
        text = ""
        shift_state = 0
        shift_lock = 0
        zscii_flag = 0
        zscii = 0
        synonym_flag = 0
        synonym = 0
        while addr < len(self.zm.memory):
            word = self.zm.read_word(addr)
            self.zm.print_debug(3,f"debug: read word 0x{word:04x} at address 0x{addr:04x}")
            addr += 2
            zscii_flag = 0

            # Extract 5-bit characters
            for shift in [10, 5, 0]:
                char_code = (word >> shift) & 0x1F
                if synonym_flag:
                    synonym_flag = 0
                    synonym = ( synonym - 1 ) * 64
                    saddr = self.zm.read_word( self.zm.synonyms_offset + synonym + ( char_code * 2 ) ) * 2
                    syntext = self.decode_string( saddr )
                    self.zm.print_debug(3,f"debug: synonym at 0x{saddr:04x} is '{syntext}'")
                    text += syntext
                    shift_state = shift_lock
                elif zscii_flag:
                    """
                    If this is the first part ZSCII ten-bit code then remember it.
                    Because the codes are only 5 bits you need two codes to make
                    one eight bit ASCII character. The first code contains the
                    top 5 bits (although only 3 bits are used at the moment).
                    The second code contains the bottom 5 bits.
                    """
                    if zscii_flag == 1:
                        zscii_flag += 1
                        zscii = char_code << 5
                    else:
                        """
                        If this is the second part of a ten-bit ZSCII code then assemble the
                        character from the two codes and output it.
                        """
                        zscii_flag = 0
                        self.zm.print_debug(3,f"write_char: 0x{zscii|charcode:02x} ({chr(zscii|charcode)}")
                        self.write_zchar( zscii | char_code)
                elif char_code > 5:
                    char_code -= 6
                    if shift_state == 2 and char_code == 0:
                        zscii_flag = 1
                    elif shift_state == 2 and char_code == 1:
                        text += "\r\n"
                    else:
                        #print(f"0x{char_code:02x}=>'{v3_lookup_table[shift_state][char_code]}'")
                        text+= v3_lookup_table[shift_state][char_code]
                    shift_state = shift_lock
                else:
                    if char_code == 0:
                        text += " "
                    else:
                        if char_code < 4:
                            synonym_flag = 1
                            synonym = char_code
                        else:
                            shift_state = char_code - 3
                            shift_lock = 0

            if (word & 0x8000) != 0:  # End bit set
                break

        return text

    def skip_string(self, addr):
        """Skip over string and return new address"""
        while addr < len(self.zm.memory):
            word = self.zm.read_word(addr)
            addr += 2
            if word & 0x8000:  # End bit set
                break
        return addr

    # Placeholder implementations for other opcodes
    #def op_catch(self, operands): pass
    def op_catch(self, operands):
        print("op_catch() not yet supported")
        sys.exit()

    def op_get_sibling(self, operands):
        self.zm.print_debug(3,f"op_get_sibling({operands[0]})")
        obj = operands[0]
        next = self.read_object(self.get_object_address(obj), object_next)
        self.zm.print_debug(3,f"sibling is {next}")
        self.store_result(next)
        self.branch(next != 0)

    """
    Load the child object pointer of an object and jump if the child pointer is
    not NULL.
    """
    def op_get_child(self, operands):
        self.zm.print_debug(3,f"op_get_child({operands[0]})")
        obj = operands[0]
        child = self.read_object(self.get_object_address(obj), object_child)
        self.zm.print_debug(3,f"child is {child}")
        self.store_result(child)
        self.branch(child != 0)

    def op_get_parent(self, operands):
        self.zm.print_debug(3,f"op_get_parent({operands[0]})")
        self.print_object(operands[0])
        objp = self.get_object_address(operands[0])
        result = self.zm.read_byte(objp + object_parent)
        self.zm.print_debug(3,f"op_get_parent() returns {result}")
        self.store_result(result)
        #specifier = self.zm.read_byte(self.zm.pc)
        #self.zm.pc += 1
        #self.write_variable(specifier,parent)

    #def op_get_prop_len(self, operands): pass
    def op_get_prop_len(self, operands):
        prop_addr = operands[0]
        if prop_addr == 0:
            self.store_result(0)
            return

        # Back up the property pointer to the property id */
        prop_addr -= 1
        value = self.zm.read_byte(prop_addr)

        if h_type <= 3:
            value = ( value >>  5 ) + 1
        elif not (value & 0x80) :
            value = ( value >>  6 ) + 1
        else:
            value = value & property_size_mask
            if value == 0:
                value = 64 # spec 1.0
        self.store_result( value )

    def op_inc(self, operands):
        result = self.read_variable(operands[0])
        result += 1
        self.write_variable(operands[0],result)

    def op_dec(self, operands):
        result = self.read_variable(operands[0])
        result -= 1
        self.write_variable(operands[0],result)

    """Print using a real address. Real addresses are just offsets into the data region."""
    def op_print_addr(self, operands):
        address = abs(operands[0])
        text = self.decode_string(address)
        self.zm.print_text(text)

    def op_ret(self, operands):
        """Return from subroutine. Restore FP and PC from stack"""
        self.return_from_routine(operands[0])

    def op_jump(self, operands):
        ptr = operands[0]
        if ptr > 0 and ptr & 0x8000 != 0:
            # negative #, make it so
            ptr = ptr - 0x10000
        self.zm.print_debug(3,f"jump from 0x{self.zm.pc:04X} to 0x{(self.zm.pc+ptr):04X}")
        self.zm.pc += ptr - 2

    """Convert packed address to real address"""
    def op_print_paddr(self, operands):
        address = abs(operands[0]) * address_scaler
        text = self.decode_string(address)
        self.zm.print_text(text)

    def op_not(self, operands):
        result = ~operands[0]
        self.store_result(result)

    def op_dec_chk(self, operands):
        if len(operands) >= 2:
            result = self.read_variable(operands[0])
            result -= 1
            self.write_variable(operands[0],result)
            self.branch(result < operands[1])

    def op_inc_chk(self, operands):
        if len(operands) >= 2:
            result = self.read_variable(operands[0])
            result += 1
            self.write_variable(operands[0],result)
            self.branch(result > operands[1])

    def op_jin(self, operands):
        objp = self.get_object_address(operands[0])
        parent = self.zm.read_byte(objp + object_parent)
        #self.op_get_parent([operands[0]])
        #parent = self.read_variable(0)
        n = operands[1]
        self.zm.print_debug(3,f"op_jin(): {parent} {n}")
        # not sure why but this is to avoid reading branch byte if false:
        #if(parent == n):
        self.branch(parent == n)

    def op_test(self, operands):
        self.branch((( ~operands[0] ) & operands[1]) == 0)

    def op_or(self, operands):
        result = 0
        if len(operands) >= 2:
            result = operands[0] | operands[1]
        self.store_result(result)

    def op_and(self, operands):
        result = 0
        if len(operands) >= 2:
            result = operands[0] & operands[1]
        self.store_result(result)

    def get_object_address(self, obj):
        offset = self.zm.object_table_addr + (max_properties - 1) * 2 + (obj - 1) * object_size
        return offset

    def op_test_attr(self, operands):
        """ Test if an attribute bit is set."""
        obj = operands[0]
        bit = operands[1]
        objp = self.get_object_address(obj) + (bit>>3)
        value = self.zm.read_byte(objp)
        self.branch(( value >> ( 7 - ( bit & 7 ) ) ) & 1)

    def op_set_attr(self, operands):
        obj = operands[0]
        bit = operands[1]
        # get attribute address
        objp = self.get_object_address(obj) + (bit>>3)
        # load attribute byte
        value = self.zm.read_byte(objp)
        # set attribute bit
        value |= 1 << ( 7 - ( bit & 7 ) )
        self.zm.write_byte(objp,value)

    def op_clear_attr(self, operands):
        obj = operands[0]
        bit = operands[1]
        # get attribute address
        objp = self.get_object_address(obj) + (bit>>3)
        # load attribute address
        value = self.zm.read_byte(objp)
        # clear attribute bit
        value &= ~ ( 1 << ( 7 - ( bit & 7 ) ) )
        # store attribute byte
        self.zm.write_byte(objp,value)

    """
    Insert object 1 as the child of object 2 after first removing it from its
    previous parent. The object is inserted at the front of the child object
    chain.
    """
    def op_insert_obj(self, operands):
        self.zm.print_debug(3,f"op_insert_obj({operands[0]} {operands[1]})")
        obj1 = operands[0]
        obj2 = operands[1]
        # Get addresses of both objects
        obj1p = self.get_object_address(obj1)
        obj2p = self.get_object_address(obj2)

        # Remove object 1 from current parent

        self.remove_object(obj1)

        # Make object 2 object 1's parent
        self.write_object(obj1p, object_parent, obj2)

        # Get current first child of object 2
        child2 = self.read_object(obj2p, object_child)

        # Make object 1 first child of object 2 *
        self.write_object(obj2p, object_child, obj1)

        # If object 2 had children then link them into the next child field of object 1
        if child2 != 0:
            self.write_object(obj1p, object_next, child2)

    """
    Load a word from an array of words
    """
    def op_loadw(self, operands):
        result = self.zm.read_word(operands[0] + operands[1] * 2)
        self.store_result(result)

    """
    Load a byte from an array of bytes
    """
    def op_loadb(self, operands):
        result = self.zm.read_byte(operands[0] + operands[1])
        self.store_result(result)

    """
    Load a property from a property list. Properties are held in list sorted by
    property id, with highest ids first. There is also a concept of a default
    property for loading only. The default properties are held in a table pointed
    to be the object pointer, and occupy the space before the first object.
    """
    def op_get_prop(self, operands):

        obj = operands[0]
        prop = operands[1]
        # Load address of first property
        prop_addr = self.get_property_addr(obj)

        # Scan down the property list
        while True:

            value = self.zm.read_byte( prop_addr )
            if ( value & property_mask ) <= prop:
                break
            prop_addr = self.get_next_prop( prop_addr )

        # If the property ids match then load the first property
        if  ( value & property_mask ) == prop:
            prop_addr += 1
            # Only load first property if it is a byte sized property
            if h_type <= 3 and not ( value & 0xe0 ) or h_type >= 4 and not ( value & 0xc0 ):
                bprop_val = self.zm.read_byte( prop_addr )
                wprop_val = bprop_val
            else:
                wprop_val = self.zm.read_word( prop_addr )
        else: # property not found
            #Calculate the address of the default property
            prop_addr = self.zm.object_table_addr + ( ( prop - 1 ) * 2 );
            wprop_val = self.zm.read_word( prop_addr );

        # store the property value

        specifier = self.zm.read_byte(self.zm.pc)
        self.zm.pc += 1
        self.write_variable(specifier,wprop_val)

    """
    Load the address address of the data associated with a property.
    """
    def op_get_prop_addr(self, operands):
        obj = operands[0]
        prop = operands[1]

        # load address of first property
        prop_addr = self.get_property_addr(obj)

        while(True):
            value = self.zm.read_byte(prop_addr)
            if (value & property_mask) <= prop:
                break
            prop_addr = self.get_next_prop(prop_addr)

        # if the property id was found, cal the prop addr, else return zero
        if (value & property_mask) == prop:
            if (h_type >= 4 and (value&0x80)):
                prop_addr += 1
            self.store_result(prop_addr + 1)
        else:
            # No property found, just return 0
            self.store_result(0)

    """
    Load the property after the current property. If the current property is zero
    then load the first property.
    """
    def op_get_next_prop(self, operands):
        obj = operands[0]
        prop = operands[1]
        # load address of first property
        prop_addr = self.get_property_addr(obj)

        # if the property id is non-zero then find the next property
        if prop != 0:
            # Scan down the property list while the target property id is less
            # than the property id in the list */
            while True:
                value = self.zm.read_byte( prop_addr )
                prop_addr = self.get_next_prop( prop_addr );
                condition = ( value & property_mask ) > prop
                if not condition:
                    break

            # If the property id wasn't found then complain
            if ( value & property_mask ) !=  prop:
                self.zm.print_error("load_next_property(): No such property")
                sys.exit()

        #cReturn the next property id
        value = self.zm.read_byte( prop_addr )
        self.store_result( ( value & property_mask ) )

    def op_mul(self, operands):
        """multiply 2 numbers"""
        if len(operands) >= 2:
            a = operands[0] if operands[0] < 32768 else operands[0] - 65536
            b = operands[1] if operands[1] < 32768 else operands[1] - 65536
            result = (a * b) % 0x10000
            self.store_result(result)

    def op_div(self, operands):
        """divide 2 numbers"""
        if len(operands) >= 2:
            a = operands[0] if operands[0] < 32768 else operands[0] - 65536
            b = operands[1] if operands[1] < 32768 else operands[1] - 65536
            if(b == 0):
                self.zm.print_error("divide by zero error: Result set to 32767 (0x7fff).") # need better error routine
                result = 32767;
            else:
                result = int(a / b) & 0xFFFF
            self.store_result(result)

    def op_mod(self, operands):
        """mod 2 numbers"""
        if len(operands) >= 2:
            if(operands[1] == 0):
                self.zm.print_error("mod by zero error: Result set to 0.") # need better error routine
                result = 0;
            else:
                result = (operands[0] % operands[1]) & 0xFFFF
            self.store_result(result)

    def op_call(self, operands):
        if operands[0] == 0:
            self.store_result(0)
        else:
            #"All operands are assumed to be unsigned numbers, unless stated otherwise",
            # so commenting this out for now
            #for i in range(1,len(operands)):
            #    if operands[i] > 0 and operands[i] & 0x8000:
            #        operands[i] = operands[i] - 0x10000 # make negative
            f = Frame()
            f.return_pointer = self.zm.pc
            if len(self.zm.call_stack) >= self.zm.STACK_SIZE:
                self.zm.print_error("stack is out of memory")
                sys.exit()
            self.zm.print_debug(3,f"in op_call(), pc=0x{self.zm.pc:04X}")

            self.zm.pc = operands[0] * address_scaler
            argc = len(operands)
            #Read argument count and initialise local variables
            args = self.zm.read_byte(self.zm.pc)
            self.zm.pc += 1
            f.arg_count = argc - 1
            #f.stack = []
            f.count = argc
            f.local_vars = [0] * 15
            i = 1
            argc = argc - 1 # don't include first operand
            while args > 0:
                args -= 1
                if h_type < 4:
                    arg = self.zm.read_word(self.zm.pc)
                    self.zm.pc += 2
                    if arg > 0 and arg & 0x8000 != 0:
                        arg = arg - 0x10000 # make negative
                    if argc > 0:
                        value = operands[i]
                        self.zm.print_debug(3,f"operand[{i}] is {value}")
                        f.local_vars[i-1] = value
                    else:
                        f.local_vars[i-1] = arg
                    argc -= 1
                    self.zm.print_debug(3,f"local var {i-1} is {f.local_vars[i-1]}")
                    i += 1
            self.zm.call_stack.append(f)
            self.zm.print_debug(3,f"new frame {len(self.zm.call_stack)}:")
            self.print_frame(f,"test")
            self.zm.print_debug(3,f">> stack size # {len(self.zm.call_stack)} (append)")

    def op_storew(self, operands):
        """Store a word"""
        addr = operands[0]
        offset = operands[1]
        value = operands[2]
        addr2 = addr + offset * 2
        if addr > len(self.zm.story_data):
            self.zm.print_error("Attempted to write outside of data area")
            sys.exit()
        self.zm.write_word(addr2, value)

        #self.zm.write_byte(operands[0]+2*operands[1],operands[2])


    def op_storeb(self, operands):
        """Store a byte """
        self.zm.write_byte(operands[0]+operands[1],operands[2])

    def op_put_prop(self, operands):
        """Store a property value in a property list. The property must exist in the
        property list to be replaced."""
        obj = operands[0]
        prop = operands[1]
        setvalue = operands[2]
        # load address of first property
        prop_addr = self.get_property_addr(obj)
        while True:
            value = self.zm.read_byte( prop_addr)
            self.zm.print_debug(3,f"value:{value} property_mask:{property_mask} prop:{prop}")
            if(value & property_mask ) <= prop:
                break
            prop_addr = self.get_next_prop(prop_addr)
            if value & property_mask <= prop:
                break

        # if the property id wasn't found then complain
        if (value & property_mask) != prop:
            self.vm.print_error("load_next_property(): no such property")
            sys.exit()
        # If the property id was found, store a new value, otherwise complain */
        if ( value & property_mask ) != prop:
            self.zm.print_error("error: store_property(): No such property")
            sys.exit()

        #Determine if this is a byte or word sized property
        prop_addr+=1

        if h_type <= 3 and not( value & 0xe0 ) or h_type >= 4 and not( value & 0xc0 ):
            self.zm.write_byte( prop_addr, setvalue )
        else:
            self.zm.write_word( prop_addr, setvalue )

    def op_random(self, operands):
        """generate random numbers"""
        range = operands[0]
        if range < 0:
            random.seed(range)
            result = 0
        elif range > 0:
            result = random.randint(1,range)
        else:
            random.seed(12345) #zero range?
        self.zm.print_debug(3,f"random() returns {result}")
        self.store_result(result)

    def op_push(self, operands):
        value = operands[0]
        self.zm.call_stack[-1].data_stack.append(value)

    def op_pull(self, operands):
        self.zm.print_debug(3,f"stack size: {len(self.zm.call_stack[-1].data_stack)}")
        var = operands[0]

        #not sure of this logic but it works:
        #if len(operands) > 1:
        #    self.zm.pc += 1
        value = self.zm.call_stack[-1].data_stack.pop()
        self.write_variable(operands[0],value)
        return

        if len(self.zm.call_stack[-1].data_stack) > 0:
            value = self.zm.call_stack[-1].data_stack.pop()
        else:
            self.zm.print_debug(3,"warning: data stack is empty")
            self.zm.print_error("data stack is empty in op_pull()")
            self.zm.game_running = False
            value = 0

        self.write_variable(var,value)
        return

    def op_print_obj(self, operands):
        obj = operands[0]
        if obj == 0:
            return

        # Calculate address of property list
        offset = self.get_object_address( obj )
        offset += property_offset

        # Read the property list address and skip the count byte
        address = self.zm.read_word( offset ) + 1

        # Decode and output text at address
        text = self.decode_string( address )
        self.zm.print_text(text)

    def op_call_2s(self, operands):
        print("op_call_2s() not yet supported")
        sys.exit()
