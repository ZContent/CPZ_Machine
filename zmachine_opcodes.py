"""
Z-Machine Opcode Processor for CircuitPython
Handles Z-machine instruction execution and text processing

This module implements the core Z-machine opcodes needed for
interactive fiction games like Zork.
"""

import sys
import random

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

h_type = 3

if h_type < 4:
    address_scaler = 2;
    story_shift = 1;
    #property_mask = P3_MAX_PROPERTIES - 1;

    property_offset = 7
    max_properties = 0x20
    property_mask = max_properties - 1
    object_size = 9
    property_size_mask = 0xe0;
elif h_type < V8:
    address_scaler = 4;
    story_shift = 2;
    #property_mask = P4_MAX_PROPERTIES - 1;
    property_offset = 12
    max_properties = 0x40
    property_mask = max_properties - 1
    object_size = 14
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
        self.stack = []
        self.count = 0
        self.local_vars = [0]*15

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
        pccount = self.zm.pc
        if self.zm.pc >= len(self.zm.memory):
            raise RuntimeError("PC out of bounds")

        opcode_byte = self.zm.read_byte(self.zm.pc)
        self.zm.pc += 1

        if opcode_byte >= 0xC0:
            # Variable form: VAR
            form = VARIABLE_FORM
            opcode = opcode_byte & 0x1F
            #print("debug: varopcode byte = ",opcode)
            operand_types = self.decode_operand_types()
            operand_count = len([t for t in operand_types if t != OMITTED])
        elif opcode_byte >= 0x80:
            # Short form: 1OP or 0OP
            form = SHORT_FORM
            opcode = opcode_byte & 0x0F
            #print("debug: 1opcode byte = ",opcode)
            operand_type = (opcode_byte & 0x30) >> 4
            if operand_type == 3:
                opcode = opcode_byte & 0x3F # need to check why this is needed
                operand_count = 0
                operand_types = []
            else:
                operand_count = 1
                operand_types = [operand_type]
        else:
            # Long form: 2OP
            form = LONG_FORM
            opcode = opcode_byte & 0x1F
            #print("debug: 2opcode byte = ",opcode)
            operand_count = 2
            operand_types = [
                SMALL_CONSTANT if (opcode_byte & 0x40) == 0 else VARIABLE,
                SMALL_CONSTANT if (opcode_byte & 0x20) == 0 else VARIABLE
            ]
        """
        # Determine instruction form
        if opcode_byte < 0x80:
            # Long form: 2OP
            form = LONG_FORM
            opcode = opcode_byte & 0x1F
            #print("debug: 2opcode byte = ",opcode)
            operand_count = 2
            operand_types = [
                SMALL_CONSTANT if (opcode_byte & 0x40) == 0 else VARIABLE,
                SMALL_CONSTANT if (opcode_byte & 0x20) == 0 else VARIABLE
            ]
        elif opcode_byte < 0xB0:
            # Short form: 1OP or 0OP
            form = SHORT_FORM
            opcode = opcode_byte & 0x0F
            #print("debug: 1opcode byte = ",opcode)
            operand_type = (opcode_byte & 0x30) >> 4
            if operand_type == 3:
                operand_count = 0
                operand_types = []
            else:
                operand_count = 1
                operand_types = [operand_type]
        elif opcode_byte < 0xC0:
            # Variable form: VAR
            form = VARIABLE_FORM
            opcode = opcode_byte & 0x1F
            #print("debug: varopcode byte = ",opcode)
            operand_types = self.decode_operand_types()
            operand_count = len([t for t in operand_types if t != OMITTED])
        else:
            # Variable form: VAR
            form = VARIABLE_FORM
            opcode = opcode_byte & 0x3F
            print("debug: varopcode byte = ",opcode)
            operand_types = self.decode_operand_types()
            operand_count = len([t for t in operand_types if t != OMITTED])
            print("debug: operand_count:",operand_count, "operand_types:",operand_types)
        """
        # Fetch operands
        operands = []
        for op_type in operand_types:
            if op_type == OMITTED:
                break
            elif op_type == LARGE_CONSTANT:
                value = self.zm.read_word(self.zm.pc)
                #print(f"debug fetch instruction: read large constant: pc=0x{self.zm.pc:02X}, value={value}");
                self.zm.pc += 2
                operands.append(value)
            elif op_type == SMALL_CONSTANT:
                value = self.zm.read_byte(self.zm.pc)
                #print(f"debug fetch instruction: read small constant: pc=0x{self.zm.pc:02X}, value={value}");
                self.zm.pc += 1
                operands.append(value)
            elif op_type == VARIABLE:
                var_num = self.zm.read_byte(self.zm.pc)
                #print(f"debug fetch instruction: read variable: pc=0x{self.zm.pc:02X}, var_num={var_num}");
                self.zm.pc += 1
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
        print(f"## frame {i}##")
        if hasattr(frame,"return_pointer"):
            print(f"return_pointer: 0x{frame.return_pointer:02X}")
        if hasattr(frame,"result_var"):
            print(f"result_var: {frame.result_var}")
        if hasattr(frame,"variable"):
            print("variable:",frame.variable)
        if hasattr(frame,"count"):
            print("local var count:",frame.count)
        if hasattr(frame,"local_vars"):
            print("local_vars:",frame.local_vars)
        if hasattr(frame,"stack"):
            print("frame stack:",frame.stack)
        print("## end ##")

    def print_frame_stack(self):
            print("### frame stack ###")
            for i in range(len(self.zm.call_stack)):
                self.print_frame(self.zm.call_stack[i],i)
            print("### end ###")

    def read_variable(self, var_num):
        """Read value from variable"""
        print("debug: read_variable()",var_num)
        if var_num == 0:
            # Stack variable
            #print("debug: read stack variable")
            if self.zm.call_stack:
                f = self.zm.call_stack[-1]
                #self.print_frame(f,len(self.zm.call_stack))
                if(len(f.stack) > 0):
                    return f.stack[-1]
                    #return self.zm.call_stack[-1].get('stack', []).pop() if self.zm.call_stack[-1].get('stack') else 0
                else:
                    return 0
            return 0
        elif var_num <= 15:
            # Local variable
            #print("debug: read local var")
            f = self.zm.call_stack[-1]
            if hasattr(f,"local_vars"):
                #print(f"debug: read local var {var_num - 1}: ",f.local_vars[var_num - 1],f.local_vars)
                return f.local_vars[var_num - 1]

            return 0
        else:
            # Global variable
            global_index = var_num - 16
            addr = self.zm.variables_addr+global_index*2
            #print(f"debug: index:{global_index}, var mem start: 0x{self.zm.variables_addr:04X}, address: 0x{addr:04X}")
            #value = self.zm.memory[addr] << 8 | self.zm.memory[addr+1]
            value = self.zm.read_word(addr)
            #print(f"read global var {global_index} from 0x{addr:04x}: {value}")
            return value

    def write_variable(self, var_num, value):
        """Write value to variable"""
        print("debug: write_variable() ", var_num, " ", value)
        value = value & 0xFFFF  # Ensure 16-bit value

        if var_num == 0:
            # Stack variable
            #print("debug: write stack variable")
            if len(self.zm.call_stack) > 0:
                #if 'stack' not in self.zm.call_stack[-1]:
                f = self.zm.call_stack[-1]
                if hasattr( f,"stack"):
                    f.stack.append(value)
        elif var_num <= 15:
            # Local variable
            if value > 0 and (value & 0x800) != 0:
                value = value - 0x10000 # make negative
            f = self.zm.call_stack[-1]
            if hasattr(f,"local_vars"):
                f.local_vars[var_num -1 ] = value
                #print(f"debug: write local var {var_num - 1}: {value}",f.local_vars)
        else:
            # Global variable
            global_index = var_num - 16
            addr = self.zm.variables_addr + global_index*2
            #print(f"debug: index:{global_index}, var mem start: 0x{self.zm.variables_addr:04X}, address: 0x{addr:04X}")
            self.zm.write_word(addr, value)
            #print(f"write global var {global_index} to 0x{addr:04x}: {value}")

    def execute_instruction(self):
        """Execute one Z-machine instruction"""

        try:
            opcode, operands, form, pccount, opcode_byte = self.fetch_instruction()
            if self.instruction_count == 0: # create initial frame the first time
                f = Frame()
                f.return_pointer = self.zm.read_word(0x06)  # Initial PC
                print("debug: ptr: ", f.return_pointer)
                print(f"debug 2: 0x{self.zm.memory[0x06]:02x}")
                self.zm.call_stack.append(f)
                print(f"debug: initial frame {len(self.zm.call_stack)}:")
                self.print_frame(f,0)
            self.instruction_count += 1
            if self.instruction_count > 200:
                print("debug: 200 instruction limit reached")
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
                full_opcode = 0x20 | opcode  # VAR opcodes

            self.zm.opcode = full_opcode
            # Execute opcode
            if full_opcode in self.opcodes:
                print(f"**start {self.instruction_count}:", self.opcodes[full_opcode][1],operands,f"pc:0x{(self.zm.pc-pccount):04X}",f"opcode:0x{opcode_byte:02X}/0x{opcode:02X}/0x{full_opcode:02X}")
                self.opcodes[full_opcode][0](operands)
                print(f"**end",self.opcodes[full_opcode][1],f"pc:0x{(self.zm.pc):04X}")
            else:
                print(f"Unimplemented opcode:0x{opcode:02X}/0x{full_opcode:02X} pc:0x{(self.zm.pc-pccount):04X}")
                sys.exit()

        except Exception as e:
            print(f"Execution error at PC 0x{self.zm.pc:04X}: {e}")
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
        print("debug: branch()", condition)
        print(f"debug: pc = 0x{self.zm.pc:02X}")

        branch_byte = self.zm.read_byte(self.zm.pc)
        self.zm.pc = self.zm.pc + 1
        print(f"debug: branch_byte 1:0x{branch_byte:02X}")

        branch_on_true = condition
        if (branch_byte & 0x80) == 0:
            branch_on_true = not branch_on_true
        branch_offset = branch_byte & 0x3F
        print("debug: branch_on_true:",branch_on_true)
        print(f"debug: pc = 0x{self.zm.pc:02X}")
        if (branch_byte & 0x40) == 0:
            # Two-byte offset
            second_byte = self.zm.read_byte(self.zm.pc)
            self.zm.pc += 1
            print(f"debug: branch_byte 2:0x{second_byte:02X}")
            branch_offset = ((branch_byte << 8) | second_byte)
            if branch_offset & 0x2000:
                branch_offset |= 0xC000  # Sign extend
            if branch_offset > 0 and branch_offset & 0x8000 :
                branch_offset -= 0x10000 # make negative
            print(f"debug: branch_offset=0x{branch_offset:0X}")
        if branch_on_true == True:
            print("debug: branch_on_true:",branch_on_true)
            print(f"debug: branch offset is 0x{branch_offset:04X}")
            if branch_offset == 0:
                self.op_rfalse([])
            elif branch_offset == 1:
                self.op_rtrue([])
            else:
                self.zm.pc += branch_offset - 2
        print(f"debug: return branch(), branch_offset = 0x{branch_offset:04X}, pc = 0x{self.zm.pc:04X}")

    def get_byte(self, offset):
        """get byte in memory array"""
        print("debug: get_byte()", offset)
        value = self.zm.memory[offset]
        print("debug: get_byte() returns",value)
        return value

    def get_word(self, offset):
        """get word in memory array"""
        print("debug: get_word(): ",offset)
        value = self.zm.memory[offset] << 8
        value += self.zm.memory[offset + 1]
        print("debug: get_word() returns",value)
        return value

    def set_word(self, offset, value):
        """set word in memory array"""
        print("debug: set_word(): ",offset, value)
        if (offset + 1) > len(self.zm.memory):
            print("error: maximum memory reached")
            exit(0)
        self.zm.memory[offset] = (value >> 8) &0xff
        self.zm.memory[offset+1] = value &0xff
        print("debug: set_word() sets value",value," at offset",offset)

    def get_object_addr(self, obj):
        """Calculate the address of an object in the data area."""
        print("debug: get_object_addr()",obj)
        offset = self.zm.object_table_addr + ( ( max_properties - 1 ) * 2 ) + ( ( obj - 1 ) * object_size)
        print("debug: ",self.zm.object_table_addr, max_properties, obj, object_size)
        print("debug: get_object_addr() returns",offset)
        return offset

    def get_property_addr(self, obj):
        """Calculate the address of the start of the property list associated with an object."""
        print("debug: get_property_addr() ",obj)
        object_addr = self.get_object_addr(obj)+ property_offset
        prop_addr = self.get_word( object_addr)
        size = self.get_byte( prop_addr )
        print("debug: object:",obj, "object_addr:",object_addr,"prop_addr:", prop_addr, "size:",size)
        value = prop_addr + ( size * 2 ) + 1
        print("debug get_property_addr() returns",value)
        return value

    def get_next_prop(self, prop_addr):
        """Calculate the address of the next property in a property list."""
        print("debug: get_next_prop()", prop_addr)
        value = self.get_byte( prop_addr )
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

    def op_print(self, operands):
        """Print literal string"""
        text = self.decode_string(self.zm.pc)
        self.zm.print_text(text)
        #print("debug: string:",text)
        # Skip over the string
        self.zm.pc = self.skip_string(self.zm.pc)

    def op_print_ret(self, operands):
        """Print literal string and return true"""
        self.op_print(operands)
        self.zm.print_text("\n")
        self.op_rtrue(operands)

    def op_ret_popped(self, operands):
        """Return popped value from stack"""
        if self.zm.call_stack and 'stack' in self.zm.call_stack[-1]:
            variable = self.zm.call_stack[-1]['stack'].pop()
            value = variable
        else:
            value = 0
        self.return_from_routine(value)

    def op_quit(self, operands):
        """Quit the game"""
        self.zm.game_running = False

    def op_new_line(self, operands):
        """Print newline"""
        self.zm.print_text("\r\n")

    def op_jz(self, operands):
        """Jump if zero"""
        if operands:
            self.branch(operands[0] == 0)

    def op_je(self, operands):
        """Jump if equal"""
        print(f"debug: op_je() pc = 0x{self.zm.pc:04X}")
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

    def op_sread(self, operands):
        """Read string from user"""
        if len(operands) >= 2:
            text_buffer = operands[0]
            parse_buffer = operands[1] if len(operands) > 1 else 0

            # Get user input (simplified)
            user_input = self.zm.get_input()

            # Store in text buffer (simplified)
            max_len = self.zm.read_byte(text_buffer)
            input_bytes = user_input.encode('ascii', errors='ignore')[:max_len]

            self.zm.write_byte(text_buffer + 1, len(input_bytes))
            for i, byte_val in enumerate(input_bytes):
                self.zm.write_byte(text_buffer + 2 + i, byte_val)

            # Parse buffer handling would go here (simplified)

    def store_result(self, value):
        """Store result of instruction"""
        result_var = self.zm.read_byte(self.zm.pc)
        self.zm.pc += 1
        self.write_variable(result_var, value)

    def return_from_routine(self, value):
        """Return from current routine"""
        print("debug: return_from_routine()",value)

        if self.zm.call_stack:
            #self.zm.pc = self.zm.call_stack[-1].get('stack', []).pop() if self.zm.call_stack[-1].get('stack') else 0
            # get operand count
            print(f"debug: pop frame {len(self.zm.call_stack)}:")
            #self.print_frame_stack()
            #self.zm.call_stack.pop()
            f = self.zm.call_stack.pop()
            #self.print_frame(f,len(self.zm.call_stack))
            if len(self.zm.call_stack) == 0:
                self.zm.print_error("call stack is empty")
                self.zm.game_running = False
                return

            # restore pc
            newpc = f.return_pointer
            print(f"debug: pointer from 0x{self.zm.pc:04X} to 0x{newpc:04X}")
            self.zm.pc = newpc
        else:
            self.zm.game_running = False
        print("debug: return from return_from_routine()")

    def decode_string(self, addr):
        """Decode Z-machine string"""
        text = ""
        shift_state = 0
        shift_lock = 0
        zscii_flag = 0
        zscii = 0
        synonym_flag = 0
        synonym = 0
        while addr < len(self.zm.memory):
            word = self.zm.read_word(addr)
            #print(f"debug: read word 0x{word:02X} at address 0x{addr:04X}")
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
                    #print(f"debug: synonym at 0x{saddr:04x} is '{syntext}'")
                    text += syntext
                    shift_state = shift_lock
                elif zscii_flag:
                    self.zm.print_error("zscii_flag not yet supported")
                    sys.exit()
                elif char_code > 5:
                    char_code -= 6
                    if shift_state == 2 and char_code == 0:
                        zscii_flag = 1
                    elif shift_state == 2 and char_code == 1:
                        self.zm.print_text("\r\n")
                    else:
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

            if word & 0x8000:  # End bit set
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

    #def op_get_sibling(self, operands): pass
    def op_get_sibling(self, operands):
        print("op_get_sibling() not yet supported")
        sys.exit()

    #def op_get_child(self, operands): pass
    def op_get_child(self, operands):
        print("op_get_child() not yet supported")
        sys.exit()

    #def op_get_parent(self, operands): pass
    def op_get_parent(self, operands):
        print("op_get_parent() not yet supported")
        sys.exit()

    #def op_get_prop_len(self, operands): pass
    def op_get_prop_len(self, operands):
        result = self.get_byte(operands[0]) >> 5
        self.store_result(result)

    #def op_inc(self, operands): pass
    def op_inc(self, operands):
        result = operands[0] + 1
        self.store_result(result)

    #def op_dec(self, operands): pass
    def op_dec(self, operands):
        result = operands[0] - 1
        self.store_result(result)

    #def op_print_addr(self, operands): pass
    def op_print_addr(self, operands):
        """Print using a real address. Real addresses are just offsets into the data region."""
        print("debug: op_print_addr()",operands)
        address = operands[0]
        print("debug: string: ",self.decode_string(self.zm.pc))
        print("op_print_addr() not yet supported")
        sys.exit()

    #def op_ret(self, operands): pass
    def op_ret(self, operands):
        """Return from subroutine. Restore FP and PC from stack"""
        print("debug: op_ret()",operands)
        self.return_from_routine(operands[0])

    #def op_jump(self, operands): pass
    def op_jump(self, operands):
        print("op_jump()", operands[0])
        ptr = operands[0]
        if ptr > 0 and ptr & 0x8000 != 0:
            # negative #, make it so
            ptr = ptr - 0x10000
        print(f"debug: jump from 0x{self.zm.pc:04X} to 0x{(self.zm.pc+ptr):04X}")
        self.zm.pc += ptr - 2

    #def op_print_paddr(self, operands): pass
    def op_print_paddr(self, operands):
        print("op_print_paddr() not yet supported")
        sys.exit()

    #def op_not(self, operands): pass
    def op_not(self, operands):
        print("op_not()",operands[0])
        result = ~operands[0]
        self.store_result(result)

    #def op_dec_chk(self, operands): pass
    def op_dec_chk(self, operands):
        result = operands[0] - 1
        self.store_result(result)
        if len(operands) >= 2:
            # Convert to signed 16-bit
            a = result if result < 32768 else result - 65536
            b = operands[1] if operands[1] < 32768 else operands[1] - 65536
            self.branch(a < b)

    #def op_inc_chk(self, operands): pass
    def op_inc_chk(self, operands):
        print("op_inc_chk() not yet supported")
        sys.exit()

    #def op_jin(self, operands): pass
    def op_jin(self, operands):
        print("op_jin() not yet supported")
        sys.exit()

    #def op_test(self, operands): pass
    def op_test(self, operands):
        self.branch((( ~operands[0] ) & operands[1]) == 0)

    #def op_or(self, operands): pass
    def op_or(self, operands):
        print("op_or()",operands[0])
        result = 0
        if len(operands) >= 2:
            result = operands[0] | operands[1]
        self.store_result(result)

    #def op_and(self, operands): pass
    def op_and(self, operands):
        print("op_or()",operands[0])
        result = 0
        if len(operands) >= 2:
            result = operands[0] & operands[1]
        self.store_result(result)

    def get_object_address(self, obj):
        offset = self.zm.object_table_addr + (max_properties - 1) * 2 + (obj - 1) * object_size
        return offset

    #def op_test_attr(self, operands): pass
    def op_test_attr(self, operands):
        """ Test if an attribute bit is set."""
        obj = operands[0]
        bit = operands[1]
        objp = self.get_object_address(obj) + (bit>>3)
        value = self.zm.read_byte(objp)
        self.branch(( value >> ( 7 - ( bit & 7 ) ) ) & 1)

    #def op_set_attr(self, operands): pass
    def op_set_attr(self, operands):
        print("op_set_attr() not yet supported")
        sys.exit()

    #def op_clear_attr(self, operands): pass
    def op_clear_attr(self, operands):
        print("op_clear_attr() not yet supported")
        sys.exit()

    #def op_insert_obj(self, operands): pass
    def op_insert_obj(self, operands):
        print("op_insert_obj() not yet supported")
        sys.exit()

    #def op_loadw(self, operands): pass
    def op_loadw(self, operands):
        result = self.zm.read_word(operands[0] + operands[1] * 2)
        self.store_result(result)

    #def op_loadb(self, operands): pass
    def op_loadb(self, operands):
        result = self.zm.read_byte(operands[0] + operands[1])
        self.store_result(result)

    #def op_get_prop(self, operands): pass
    def op_get_prop(self, operands):
        print("op_get_prop() not yet supported")
        sys.exit()

    #def op_get_prop_addr(self, operands): pass
    def op_get_prop_addr(self, operands):
        print("op_get_prop_addr() not yet supported")
        sys.exit()

    #def op_get_next_prop(self, operands): pass
    def op_get_next_prop(self, operands):
        print("op_get_next_prop() not yet supported")
        sys.exit()

    def op_mul(self, operands):
        """multiply 2 numbers"""
        if len(operands) >= 2:
            result = (operands[0] * operands[1]) % 0x10000
            self.store_result(result)

    def op_div(self, operands):
        """divide 2 numbers"""
        # future: check signed numbers?
        if len(operands) >= 2:
            if(operands[1] == 0):
                print("divide by zero error: Result set to 32767 (0x7fff).") # need better error routine
                result = 32767;
            else:
                result = (operands[0] / operands[1]) & 0xFFFF
            self.store_result(result)

    #def op_mod(self, operands): pass
    def op_mod(self, operands):
        """mod 2 numbers"""
        if len(operands) >= 2:
            if(operands[1] == 0):
                print("mod by zero error: Result set to 0.") # need better error routine
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
            f.return_pointer = self.zm.pc + 1
            if len(self.zm.call_stack) >= self.zm.STACK_SIZE:
                print("error: stack is out of memory")
                sys.exit()
            print(f"debug: in op_call(), pc=0x{self.zm.pc:04X}")

            self.zm.pc = operands[0] * address_scaler
            argc = len(operands)
            #Read argument count and initialise local variables
            args = self.zm.read_byte(self.zm.pc)
            self.zm.pc += 1
            f.arg_count = argc - 1
            f.stack = []
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
                        print(f"debug: operand[{i}] is {value}")
                        f.local_vars[i-1] = value
                    else:
                        f.local_vars[i-1] = arg
                    argc -= 1
                    print(f"debug: local var {i-1} is {f.local_vars[i-1]}")
                    i += 1
            self.zm.call_stack.append(f)
            print(f"debug: new frame {len(self.zm.call_stack)}:")
            self.print_frame(f,"test")
            print(">> stack size #", len(self.zm.call_stack),"(append)")

    #def op_storew(self, operands): pass
    def op_storew(self, operands):
        """Store a word in an array of words"""
        self.set_word(operands[1],operands[2])

    #def op_storeb(self, operands): pass
    def op_storeb(self, operands):
        """Store a byte in an array of bytes"""
        self.set_byte(operands[1],operands[2])

    #def op_put_prop(self, operands): pass
    def op_put_prop(self, operands):
        """Store a property value in a property list. The property must exist in the
        property list to be replaced."""
        obj = operands[0]
        prop = operands[1]
        setvalue = operands[2]
        # load address of first property
        prop_addr = self.get_property_addr(obj)
        while True:
            print("debug")
            value = self.get_byte( prop_addr)
            print(value, property_mask, prop)
            if(value & property_mask ) <= prop:
                break
            prop_addr = self.get_next_prop(prop_addr)

        # If the property id was found, store a new value, otherwise complain */
        print("debug 2: ",value, value&property_mask, prop)
        if ( value & property_mask ) != prop:
            print("error: store_property(): No such property")
            sys.exit()

        #Determine if this is a byte or word sized property
        prop_addr+=1

        if h_type <= 3 and not( value & 0xe0 ) or h_type >= 4 and not( value & 0xc0 ):
            self.set_byte( prop_addr, setvalue )
        else:
            self.set_word( prop_addr, setvalue )

    #def op_random(self, operands): pass
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
        print("debug: random() returns",result)
        self.store_result(result)

    #def op_push(self, operands): pass
    def op_push(self, operands):
        print("op_push() not yet supported")
        sys.exit()

    #def op_pull(self, operands): pass
    def op_pull(self, operands):
        print("op_pull()",operands)
        print("debug: stack size:",len(self.zm.call_stack[-1].stack))
        print("op_pull() not yet supported")
        sys.exit()
