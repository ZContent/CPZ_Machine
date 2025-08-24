"""
CircuitPython Z-Machine Implementation for Adafruit Fruit Jam
Port of A2Z Machine to CircuitPython with built-in DVI output
Based on original A2Z Machine by Dan Cogliano and JZip 2.1

Hardware Requirements:
- Adafruit Fruit Jam (RP2350B with 16MB Flash + 8MB PSRAM)
- HDMI cable connected to built-in DVI port

Features:
- Support for Z-machine versions 3, 5, and 8
- Multiple color themes (Default, Amiga, Compaq, C64, etc.)
- Full screen text display via DVI/HDMI
- Save/restore game functionality
- Drag-and-drop story file management
- USB keyboard input support

Libraries Required:
- adafruit_display_text
- adafruit_display_shapes
- adafruit_hid (for USB keyboard)
"""

import board
import picodvi
import framebufferio
import displayio
import terminalio
import sys
import os
import gc
import time
import usb_hid
from adafruit_display_text import label
from adafruit_display_shapes.rect import Rect
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
import supervisor
import storage

# Import our custom modules
from zmachine_opcodes import ZProcessor
from keyboard_handler import ZKeyboardHandler

# Z-Machine constants
SUPPORTED_VERSIONS = [3, 5, 8]
SAVE_DIR = "/saves"
STORY_DIR = "/stories"
MAX_STORY_SIZE = 1024 * 1024  # 1MB max story size (plenty of PSRAM available)

# Display configuration for Fruit Jam built-in DVI
DISPLAY_WIDTH = 640   # Take advantage of higher resolution
DISPLAY_HEIGHT = 480
COLOR_DEPTH = 8       # 8-bit color for better memory usage
CHAR_WIDTH = 8
CHAR_HEIGHT = 16
TEXT_COLS = DISPLAY_WIDTH // CHAR_WIDTH    # 80 columns
TEXT_ROWS = DISPLAY_HEIGHT // CHAR_HEIGHT  # 30 rows

# Color themes (expanded from A2Z Machine)
THEMES = {
    'default': {
        'bg': 0x000000,      # Black
        'text': 0xFFFFFF,    # White
        'status': 0x00FF00,  # Green
        'input': 0xFFFF00,   # Yellow
        'error': 0xFF0000    # Red
    },
    'amiga': {
        'bg': 0x000040,      # Dark blue
        'text': 0xFFFFFF,    # White
        'status': 0x0080FF,  # Light blue
        'input': 0xFFFF00,   # Yellow
        'error': 0xFF4040    # Light red
    },
    'compaq': {
        'bg': 0x000000,      # Black
        'text': 0x00FF00,    # Green
        'status': 0x80FF80,  # Light green
        'input': 0xFFFF00,   # Yellow
        'error': 0xFF8080    # Light red
    },
    'c64': {
        'bg': 0x4040E0,      # C64 blue
        'text': 0xA0A0FF,    # Light blue
        'status': 0xFFFFFF,  # White
        'input': 0xFFFF40,   # Light yellow
        'error': 0xFF4040    # Light red
    },
    'amber': {
        'bg': 0x000000,      # Black
        'text': 0xFFB000,    # Amber
        'status': 0xFFF000,  # Bright yellow
        'input': 0xFFFFFF,   # White
        'error': 0xFF4000    # Orange-red
    }
}

class ZMachine:
    THEMES = {
        'default': {
            'bg': 0x000000,      # Black
            'text': 0xFFFFFF,    # White
            'status': 0x00FF00,  # Green
            'input': 0xFFFF00,   # Yellow
            'error': 0xFF0000    # Red
        }
    }

    def __init__(self):
        self.debug = 0 # debug level, 0 = no debugging output
        self.DATA_SIZE = 1024*20
        self.STACK_SIZE = 1024
        self.story_data = None
        self.story_offset = 0
        self.memory = bytearray() # story data
        self.data = bytearray()*self.DATA_SIZE #strings are here
        self.pc = 0  # Program counter
        self.call_stack = []
        self.sp = self.STACK_SIZE - 2
        #self.global_vars = [0] * 240  # Z-machine global variables
        self.objects = {}
        self.dictionary = {}
        self.current_theme = 'default'
        self.display = None
        self.keyboard_handler = None
        self.processor = None
        self.input_buffer = ""
        self.output_buffer = []
        self.text_buffer = [""] * TEXT_ROWS
        self.cursor_row = 2  # Start below status line
        self.cursor_col = 0
        self.status_line = ""
        self.z_version = 0
        self.current_opcode = None # for stack trace (future)
        self.game_running = False
        self.text_labels = []

        # Z-machine header addresses
        self.dictionary_addr = 0
        self.object_table_addr = 0
        self.variables_addr = 0
        self.abbreviations_addr = 0
        self.routine_offset = 0
        self.string_offset = 0
        self.synonyms_offset = 0

        # Initialize processor and keyboard handler
        self.processor = ZProcessor(self)
        self.keyboard_handler = ZKeyboardHandler(self)

    def init_display(self):
        """Initialize DVI display on Fruit Jam"""
        try:
            displayio.release_displays()

            # Fruit Jam has built-in DVI - no HSTX adapter needed
            # Use board-specific pin definitions
            fb = picodvi.Framebuffer(
                DISPLAY_WIDTH, DISPLAY_HEIGHT,
                clk_dp=board.CKP, clk_dn=board.CKN,
                red_dp=board.D0P, red_dn=board.D0N,
                green_dp=board.D1P, green_dn=board.D1N,
                blue_dp=board.D2P, blue_dn=board.D2N,
                color_depth=COLOR_DEPTH
            )

            self.display = framebufferio.FramebufferDisplay(fb)

            # Create display groups
            self.main_group = displayio.Group()
            self.display.root_group = self.main_group

            # Create background
            theme = THEMES[self.current_theme]
            bg_bitmap = displayio.Bitmap(DISPLAY_WIDTH, DISPLAY_HEIGHT, 1)
            bg_palette = displayio.Palette(1)
            bg_palette[0] = theme['bg']
            bg_sprite = displayio.TileGrid(bg_bitmap, pixel_shader=bg_palette)
            self.main_group.append(bg_sprite)

            # Setup text display
            self.setup_text_display()

            print("Fruit Jam DVI display initialized successfully")
            return True

        except Exception as e:
            print(f"Failed to initialize DVI display: {e}")
            return False

    def setup_text_display(self):
        """Setup full-screen text display"""
        theme = THEMES[self.current_theme]

        # Status line (row 0)
        self.status_label = label.Label(
            terminalio.FONT,
            text=" " * TEXT_COLS,
            color=theme['status'],
            x=0, y=8
        )
        self.main_group.append(self.status_label)

        # Separator line (row 1)
        separator_rect = Rect(0, CHAR_HEIGHT, DISPLAY_WIDTH, 1, fill=theme['text'])
        self.main_group.append(separator_rect)

        # Main text area (rows 2-29)
        self.text_labels = []
        for i in range(TEXT_ROWS - 2):
            text_label = label.Label(
                terminalio.FONT,
                text="",
                color=theme['text'],
                x=0, y=(i + 2) * CHAR_HEIGHT + 8
            )
            self.main_group.append(text_label)
            self.text_labels.append(text_label)

    def init_keyboard(self):
        """Initialize USB keyboard input"""
        try:
            self.keyboard = Keyboard(usb_hid.devices)
            print("USB keyboard initialized")
            return True
        except Exception as e:
            print(f"Failed to initialize keyboard: {e}")
            return False

    def load_story(self, filename):
        """Load Z-machine story file"""
        try:
            story_path = f"{STORY_DIR}/{filename}"
            sp = os.stat(story_path)
            if not sp[0]:
                raise FileNotFoundError(f"Story file not found: {filename}")
            # Check file size
            stat = os.stat(story_path)
            if stat[6] > MAX_STORY_SIZE:
                raise ValueError(f"Story file too large: {stat[6]} bytes")

            with open(story_path, 'rb') as f:
                self.story_data = f.read()

            # Parse Z-machine header
            if len(self.story_data) < 64:
                raise ValueError("Invalid story file - too short")

            self.z_version = self.story_data[0]
            if self.z_version not in SUPPORTED_VERSIONS:
                raise ValueError(f"Unsupported Z-machine version: {self.z_version}")

            # Initialize memory with story data (take advantage of PSRAM)
            self.memory = bytearray(self.story_data)

            # Pad memory to ensure we have enough space for dynamic memory
            if len(self.memory) < 65536:
                self.memory.extend(bytearray(65536 - len(self.memory)))

            # Extract key addresses from header
            self.pc = self.read_word(0x06)  # Initial PC
            self.dictionary_addr = self.read_word(0x08)
            self.object_table_addr = self.read_word(0x0A)
            self.variables_addr = self.read_word(0x0C)
            self.abbreviations_addr = self.read_word(0x18)
            self.synonyms_offset = self.read_word(24);

            # Version-specific initialization
            if self.z_version >= 4:
                self.routine_offset = self.read_word(0x28) * 8
                self.string_offset = self.read_word(0x2A) * 8
            else:
                self.routine_offset = self.string_offset = 0

            # Initialize objects and dictionary
            self.init_objects()
            self.init_dictionary()

            self.print_text(f"Loaded {filename} (Z{self.z_version})\n")
            self.print_text(f"Story size: {len(self.story_data)} bytes\n")
            self.print_text("\n")
            return True

        except Exception as e:
            self.print_error(f"Error loading story: {e}")
            return False

    def read_byte(self, addr):
        """Read byte from memory"""
        if addr < len(self.memory):
            return self.memory[addr]
        return 0

    def read_word(self, addr):
        """Read 16-bit word from memory (big-endian)"""
        if addr + 1 < len(self.memory):
            return (self.memory[addr] << 8) | self.memory[addr + 1]
        return 0

    def write_byte(self, addr, value):
        """Write byte to memory"""
        if addr < len(self.memory):
            self.memory[addr] = value & 0xFF

    def write_word(self, addr, value):
        """Write 16-bit word to memory (big-endian)"""
        if addr + 1 < len(self.memory):
            self.memory[addr] = (value >> 8) & 0xFF
            self.memory[addr + 1] = value & 0xFF

    def init_objects(self):
        """Initialize object table"""
        # Object table parsing - simplified version
        if self.object_table_addr == 0:
            return

        # Skip property defaults (31 words for v1-3, 63 for v4+)
        defaults_size = 31 if self.z_version <= 3 else 63
        obj_start = self.object_table_addr + (defaults_size * 2)

        self.objects = {}
        obj_size = 9 if self.z_version <= 3 else 14

        # Parse first 255 objects (simplified)
        for i in range(1, 256):
            obj_addr = obj_start + (i - 1) * obj_size
            if obj_addr + obj_size > len(self.memory):
                break

            # Store object address for later use
            self.objects[i] = obj_addr

    def init_dictionary(self):
        """Initialize dictionary table"""
        if self.dictionary_addr == 0:
            return

        # Read word separators
        sep_count = self.read_byte(self.dictionary_addr)
        dict_start = self.dictionary_addr + 1 + sep_count

        # Read entry length and number of entries
        entry_length = self.read_byte(dict_start)
        entry_count = self.read_word(dict_start + 1)

        self.dictionary = {
            'separators': [],
            'entries': [],
            'entry_length': entry_length,
            'start_addr': dict_start + 3
        }

        # Read separators
        for i in range(sep_count):
            self.dictionary['separators'].append(
                self.read_byte(self.dictionary_addr + 1 + i)
            )

    def print_text(self, text):
        """Print text to display"""
        if not text:
            return

        #debug
        print(text, end="")
        #end debug
        lines = text.split('\n')
        for line in lines:
            # Word wrap if necessary
            while len(line) > TEXT_COLS:
                # Find last space within column limit
                break_pos = TEXT_COLS
                for i in range(TEXT_COLS - 1, 0, -1):
                    if line[i] == ' ':
                        break_pos = i
                        break

                self.add_text_line(line[:break_pos])
                line = line[break_pos:].lstrip()

            if line or not self.text_buffer[self.cursor_row]:
                self.add_text_line(line)

    def add_text_line(self, line):
        """Add a line of text to the display"""
        if self.cursor_row >= len(self.text_labels):
            # Scroll up
            for i in range(len(self.text_labels) - 1):
                self.text_buffer[i] = self.text_buffer[i + 1]
                self.text_labels[i].text = self.text_buffer[i]
            self.cursor_row = len(self.text_labels) - 1

        self.text_buffer[self.cursor_row] = line
        self.text_labels[self.cursor_row].text = line
        self.cursor_row += 1
        self.cursor_col = 0

    def print_debug(self, level, msg):
        if self.debug >= level :
            print(f"debug: {msg}")

    def print_error(self, error_msg):
        """Print error message in error color"""
        #debug
        print(f"*** ERROR: {error_msg}")
        return
        #end debug
        theme = THEMES[self.current_theme]
        # Change text color temporarily
        current_color = self.text_labels[0].color
        if self.cursor_row < len(self.text_labels):
            temp_label = label.Label(
                terminalio.FONT,
                text=f"ERROR: {error_msg}",
                color=theme['error'],
                x=0, y=(self.cursor_row + 2) * CHAR_HEIGHT + 8
            )
            self.main_group.append(temp_label)
            self.cursor_row += 1

    def update_status_line(self, location="", score="", moves=""):
        """Update the status line"""
        theme = THEMES[self.current_theme]

        if self.z_version <= 3:
            # Score/moves format
            status_text = f" {location:<30} Score: {score:>3} Moves: {moves:>3} "
        else:
            # Time format
            status_text = f" {location:<50} {score:>10} "

        # Pad or truncate to exact width
        status_text = status_text[:TEXT_COLS].ljust(TEXT_COLS)
        self.status_label.text = status_text

    def get_input(self):
        """Get input from keyboard handler"""
        if self.keyboard_handler:
            #return input()
            return self.keyboard_handler.get_input_line()
        else:
            print("> ", end="")
            return input().strip().lower()

    def save_game(self, save_name="quicksave"):
        """Save game state"""
        try:
            os.mkdir(SAVE_DIR)
            save_path = f"{SAVE_DIR}/{save_name}.sav"

            save_data = {
                'memory': bytes(self.memory[:self.variables_addr + 480]),  # Dynamic memory only
                'pc': self.pc,
                'call_stack': self.call_stack,
                #'global_vars': self.global_vars,
                'z_version': self.z_version
            }

            # Simple binary format save (could be improved)
            with open(save_path, 'wb') as f:
                # Write header
                f.write(b'ZSAV')  # Magic number
                f.write(bytes([self.z_version]))
                f.write(self.pc.to_bytes(2, 'big'))

                # Write memory
                f.write(len(save_data['memory']).to_bytes(2, 'big'))
                f.write(save_data['memory'])

                # Write stack (simplified)
                f.write(len(self.call_stack).to_bytes(1, 'big'))
                for frame in self.call_stack:
                    f.write(frame.to_bytes(2, 'big'))

            self.print_text(f"Game saved as {save_name}")
            return True

        except Exception as e:
            self.print_error(f"Save failed: {e}")
            return False

    def restore_game(self, save_name="quicksave"):
        """Restore game state"""
        try:
            save_path = f"{SAVE_DIR}/{save_name}.sav"
            if not os.path.exists(save_path):
                raise FileNotFoundError(f"Save file not found: {save_name}")

            with open(save_path, 'rb') as f:
                # Read header
                magic = f.read(4)
                if magic != b'ZSAV':
                    raise ValueError("Invalid save file")

                version = f.read(1)[0]
                if version != self.z_version:
                    raise ValueError("Save file version mismatch")

                self.pc = int.from_bytes(f.read(2), 'big')

                # Read memory
                mem_size = int.from_bytes(f.read(2), 'big')
                mem_data = f.read(mem_size)
                self.memory[:len(mem_data)] = mem_data

                # Read stack
                stack_size = f.read(1)[0]
                self.call_stack = []
                for _ in range(stack_size):
                    frame = int.from_bytes(f.read(2), 'big')
                    self.call_stack.append(frame)

            self.print_text(f"Game restored from {save_name}")
            return True

        except Exception as e:
            self.print_error(f"Restore failed: {e}")
            return False

    def change_theme(self, theme_name):
        """Change color theme"""
        if theme_name in THEMES:
            self.current_theme = theme_name
            self.setup_text_display()  # Refresh display with new colors
            self.print_text(f"Theme changed to: {theme_name}")
        else:
            self.print_error(f"Unknown theme: {theme_name}")

    def list_stories(self):
        """List available story files"""
        try:
            files = os.listdir(STORY_DIR)
            story_files = [f for f in files if f.lower().endswith(('.z3', '.z5', '.z8', '.dat'))]

            if not story_files:
                self.print_text("No story files found.\n")
                self.print_text(f"Copy story files to {STORY_DIR}/\n")
            else:
                self.print_text("Available stories:\n")
                for i, filename in enumerate(story_files, 1):
                    self.print_text(f"  {i}. {filename}\n")

            return story_files

        except Exception as e:
            self.print_error(f"Error listing stories: {e}")
            return []

    def run_interpreter(self):
        """Main Z-machine interpreter loop"""
        self.game_running = True
        self.print_text("CircuitPython Z-Machine Interpreter\n")
        self.print_text("Based on A2Z Machine by Dan Cogliano\n")
        self.print_text("=" * 50)
        self.print_text("\n")
        # List available stories
        stories = self.list_stories()
        if not stories:
            return

        # For demo, load first story automatically
        if stories:
            if self.load_story(stories[0]):
                self.print_text("Game loaded successfully!\n")
                self.print_text("Type 'help' for interpreter commands\n")
                self.print_text("\n")

                # Start Z-machine execution
                self.execute_game()

    def execute_game(self):
        """Execute Z-machine instructions"""
        try:
            while self.game_running and self.pc < len(self.memory):
                # Execute one instruction
                if self.processor:
                    self.processor.execute_instruction()
                else:
                    # Fallback for testing
                    self.test_mode()

                # Yield control periodically
                if self.processor.instruction_count % 100 == 0:
                    time.sleep(0.001)  # Small delay to prevent blocking
            if not self.game_running :
                self.print_text("game is no longer running (interrupted?)\n")
        except KeyboardInterrupt:
            self.print_text("\nGame interrupted by user")
            self.game_running = False
        except Exception as e:
            self.print_error(f"Game execution error: {e}")
            self.game_running = False

    def test_mode(self):
        """Simple test mode when processor not available"""
        while self.game_running:
            try:
                cmd = self.get_input()

                if cmd == 'quit':
                    self.game_running = False
                elif cmd == 'save':
                    self.save_game()
                elif cmd == 'restore':
                    self.restore_game()
                elif cmd.startswith('theme '):
                    theme_name = cmd[6:]
                    self.change_theme(theme_name)
                elif cmd == 'themes':
                    self.print_text("Available themes:")
                    for theme in THEMES.keys():
                        self.print_text(f"  {theme}")
                elif cmd == 'help':
                    self.show_help()
                else:
                    # Echo command for testing
                    self.print_text(f"You typed: {cmd}")
                    self.print_text("(Full Z-machine processing not active in test mode)")

            except KeyboardInterrupt:
                self.game_running = False
            except Exception as e:
                self.print_error(f"Error: {e}")

    def show_help(self):
        """Show help information"""
        self.print_text("CircuitPython Z-Machine Commands:")
        self.print_text("  help     - Show this help")
        self.print_text("  save     - Save current game")
        self.print_text("  restore  - Restore saved game")
        self.print_text("  themes   - List available themes")
        self.print_text("  theme <name> - Change color theme")
        self.print_text("  quit     - Exit interpreter")
        self.print_text("")
        self.print_text("Game commands depend on the loaded story.")

# Initialize and run the Z-Machine
def main():
    """Main entry point"""
    print("Starting CircuitPython Z-Machine for Fruit Jam...")

    zmachine = ZMachine()

    # Initialize display
    if not zmachine.init_display():
        print("Failed to initialize display")
        return

    # Initialize keyboard
    if not zmachine.init_keyboard():
        print("Warning: Keyboard initialization failed")

    # Run the interpreter
    zmachine.run_interpreter()

    print("Z-Machine interpreter terminated")

if __name__ == "__main__":
    main()
