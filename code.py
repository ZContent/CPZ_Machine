"""
CPZ Machine for the Adafruit Fruit Jam:
A native Z Machine for the Adafruit Fruit Jam running Circuit
Python for playing Zork and similar games

Latest version of CPZ Machine can be found here:
https://github.com/ZContent/CPZ_Machine

More info on the Adafruit Fruit Jam can be found here:
https://www.adafruit.com/product/6200

Written by Dan Cogliano
Web: https://DanTheGeek.com
BlueSky: @cogliano.bsky.social

This work is based on A2Z Machine by Dan Cogliano
and JZip by John Holder

Hardware Requirements:
- Adafruit Fruit Jam (RP2350B with 16MB Flash + 8MB PSRAM)
- HDMI cable connected to built-in DVI port
- USB keyboard

Features:

- Support for different monospace font sizes to allow different
  row and column character dimensions
- Supports version 3 (.z3) games
- Game selection at startup, or starting the game automatically
  if just one game installed
- Select a retro color theme to change the font and background color
- A screen saver is enabled after an amount of time of no keyboard entry
- Save and restore games to CPSAVES partition (recommended in case
  you are eaten by a grue :-) )
- Multiple save/restore names allowed to save different locations during game
- Works as a stand-alone game or within the Fruit Jam OS environment
- Blinking cursor!

Libraries Required:
- adafruit_display_text
- adafruit_display_shapes
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

from adafruit_display_text.bitmap_label import Label
from adafruit_display_shapes.rect import Rect
import supervisor
import storage

# terminalio
from adafruit_fruitjam import peripherals
from displayio import Group
from terminalio import FONT
import settings

import gc
import supervisor
import displayio
from lvfontio import OnDiskFont
from adafruit_bitmap_font import bitmap_font
from adafruit_fruitjam.peripherals import request_display_config
# Import our custom modules
from zmachine_opcodes import ZProcessor, Frame

# Z-Machine constants
SUPPORTED_VERSIONS = [3]
SAVE_DIR = "/saves/cpz"
STORY_DIR = "stories"
MAX_STORY_SIZE = 1024 * 1024  # 1MB max story size (plenty of PSRAM available)

class ZMachine:
# Color themes (expanded from A2Z Machine)
    THEMES = {
        'trs80': {
            'bg': 0x000000,         # Black
            'text': 0xFFFFFF,       # White
            'status': 0x000000,     # Black
            'status_bg': 0xFFFFFF,  # White
        },
        'lisa': {
            'bg': 0xFFFFFF,         # White
            'text': 0x000000,       # Black
            'status': 0xFFFFFF,     # White
            'status_bg': 0x000000,  # Black
        },
        'compaq': {
            'bg': 0x000000,         # Black
            'text': 0x00FF00,       # Green
            'status': 0x000000,     # Black
            'status_bg': 0x00FF00,  #Green
        },
        'amiga': {
            'bg': 0x4040E0,         # C64 blue
            #'text': 0xA0A0FF,       # Light blue
            'text': 0xFFFFFF,       # White
            'status': 0x4040E0,     # C64 Blue
            'status_bg': 0xA0A0FF,  # Light blue
        },
        'amber': {
            'bg': 0x000000,         # Black
            'text': 0xFFB000,       # Amber
            'status': 0x000000,     # Black
            'status_bg': 0xFFB000,  # Amber
        }
    }

    def __init__(self):
        """
        debug levels (in flux)
        Preceed command with '~' to enable debug level
        i.e, "~~restore" for debug level 2 for restore command:
        0 - no debugging
        1 - opcode only
        2 - add local vars and stack
        3 - add routines
        4 - add loops
        """
        self.debug = 0 # debug level, 0 = no debugging output
        self.filename = ""
        self.save_game_name = "default"
        self.DATA_SIZE = 1024*20
        self.STACK_SIZE = 1024
        self.story_data = None
        self.story_offset = 0
        self.memory = bytearray() # story data
        self.data = bytearray()*self.DATA_SIZE #strings are here
        self.pc = 0  # Program counter
        self.call_stack = []
        self.sp = self.STACK_SIZE - 2
        #self.data_stack = []
        #self.global_vars = [0] * 240  # Z-machine global variables
        self.objects = {}
        self.dictionary = {}
        self.dictionary_size = 0
        self.dictionary_offset = 0
        self.current_theme = settings.DEFAULT_THEME
        self.display = None
        self.processor = None
        self.input_buffer = ""
        self.output_buffer = []
        self.cursor_row = -1
        self.scrolling = False
        self.skip_scroll = False
        self.cursor_col = 0
        self.status_line = ""
        self.lines_written = 0
        self.z_version = 0
        self.current_opcode = None # for stack trace (future)
        self.game_running = False
        self.font_bb = [0]*2
        self.text_labels = []
        self.line_buff = ""
        # calculated based on screen size and font size
        self.screen_width = 0 # deprecated use text_cols
        self.screen_height = 0 # deprecated use text_rows
        self.text_cols = 0
        self.text_rows = 0

        # Z-machine header addresses
        self.dictionary_addr = 0
        self.object_table_addr = 0
        self.variables_addr = 0
        self.abbreviations_addr = 0
        self.routine_offset = 0
        self.string_offset = 0
        self.synonyms_offset = 0

        # Initialize processor
        self.processor = ZProcessor(self)

        self.terminal = None

        self.line_count = 0
        self.display_background = None
        self.display_saver = None
        self.display_cursor = None

    def init_display(self):
        """Initialize DVI display on Fruit Jam"""
        try:
            displayio.release_displays()

            # Fruit Jam has built-in DVI - no HSTX adapter needed
            # Use board-specific pin definitions
            fb = picodvi.Framebuffer(
                settings.DISPLAY_WIDTH, settings.DISPLAY_HEIGHT,
                clk_dp=board.CKP, clk_dn=board.CKN,
                red_dp=board.D0P, red_dn=board.D0N,
                green_dp=board.D1P, green_dn=board.D1N,
                blue_dp=board.D2P, blue_dn=board.D2N,
                color_depth=settings.COLOR_DEPTH
            )

            self.display = framebufferio.FramebufferDisplay(fb)

            # Create display groups
            self.main_group = displayio.Group()
            self.display.root_group = self.main_group

            # Create background
            theme = self.THEMES[self.current_theme]
            bg_bitmap = displayio.Bitmap(settings.DISPLAY_WIDTH, settings.DISPLAY_HEIGHT, 1)
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
        theme = self.THEMES[self.current_theme]
        if len(settings.FONT_FILE) == 0:
            font = terminalio.FONT # 106 x 40 font
        else:
            font = bitmap_font.load_font(settings.FONT_FILE)
        bb = font.get_bounding_box()
        self.font_bb[0] = bb[0]
        self.font_bb[1] = bb[1]
        if len(bb) == 4:
            self.font_bb[1] -= bb[3]

        if self.font_bb[0] == 0:
            raise ValueError("Invalid font, must be a monospace font")
        self.text_cols = self.display.width // self.font_bb[0]
        self.text_rows = self.display.height // self.font_bb[1]
        print(f"text display: {self.text_cols} x {self.text_rows}")
        # use for background
        self.display_background = Rect(0, 0, settings.DISPLAY_WIDTH,
            settings.DISPLAY_HEIGHT,
            stroke=0,outline=None,fill=theme['bg'])

        self.main_group.append(self.display_background)
        # Status line (row 0)
        self.status_label = Label(
            font,
            text=" " * self.text_cols,
            color=theme['status'], background_color=theme['status_bg'],
            x=0, y= self.font_bb[1] // 2
        )
        self.main_group.append(self.status_label)

        #main_group = displayio.Group()
        display = supervisor.runtime.display

        # Main text area (rows 2-29)
        self.text_labels = []
        for i in range(self.text_rows - 2):
            text_label = Label(
                font,
                text="",
                color=theme['text'],
                background_color=theme['bg'],
                x=0, y=i * self.font_bb[1] + self.font_bb[1]*2
            )
            #print(f"{i}: {text_label.y}")
            self.main_group.append(text_label)
            self.text_labels.append(text_label)
        # use for cursor
        self.display_cursor = Rect(0,0,self.font_bb[0],self.font_bb[1],stroke=0,outline=None,fill=theme['text'])
        self.main_group.append(self.display_cursor)
        # use for screen saver
        self.display_saver = Rect(0, settings.DISPLAY_HEIGHT, settings.DISPLAY_WIDTH, settings.DISPLAY_HEIGHT, fill=0x000000)
        self.main_group.append(self.display_saver)

    def load_story(self, filename):
        """Load Z-machine story file"""
        try:
            self.print_text(f"Loading {filename}...")
            story_path = f"{STORY_DIR}/{filename}"
            sp = os.stat(story_path)
            if not sp[0]:
                raise RuntimeError(f"Story file not found: {filename}")
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

            self.print_text(f"Story size: {len(self.story_data)} bytes")
            self.filename = filename
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

    def show_input_prompt(self):
        """ used by non-machine routines, should match machine prompt """
        self.print_text(">")
        self.display_cursor.x = self.font_bb[0]
        self.display_cursor.y = self.text_labels[self.cursor_row].y - self.font_bb[1]//2

    def print_text(self, text):
        """Print text to display"""
        #self.print_debug(3,"print_text()")
        if len(text) > 0 and text[-1] == "\n":
            text = text[:-1]
        lines = text.split('\n')
        for line in lines:
            # Word wrap if necessary
            while len(line) > self.text_cols:
                # Find last space within column limit
                break_pos = self.text_cols
                for i in range(self.text_cols - 1, 0, -1):
                    if line[i] == ' ':
                        break_pos = i
                        break
                if break_pos < self.text_cols:
                    self.add_text_line(line[:break_pos])
                line = line[break_pos:].lstrip()

            self.add_text_line(line)
        #self.print_debug(3,"print_text() done")

    def add_text_line(self, line):
        """Add a line of text to the display"""
        #self.print_debug(3,f"add_text_line(): {line}")
        line = line.replace('\r', '\n')
        line = line.replace('\n', '')
        self.lines_written += 1
        #print(f"cursor: label {self.cursor_row} of {len(self.text_labels)} labels")
        if self.cursor_row >= len(self.text_labels) - 1:
            self.scrolling = True
        if not self.skip_scroll:
            if self.scrolling:
                # Scroll up
                #self.print_debug(3,f"scrolling display")
                for i in range(len(self.text_labels)):
                    self.text_labels[i].y -= self.font_bb[1]
                    if self.text_labels[i].y < self.font_bb[1]*2:
                        self.text_labels[i].text = ""
                        self.text_labels[i].y = (len(self.text_labels)-1) * self.font_bb[1] + 2*self.font_bb[1]
                        self.cursor_row = i
                    #self.print_debug(4,f"{i}: {self.text_labels[i].y} {'*' if self.cursor_row == i else ''}")
                #self.print_debug(3,f"scrolling display done")
            else:
                self.cursor_row = (self.cursor_row + 1) % (len(self.text_labels))
        else:
            self.skip_scroll = False

        self.text_labels[self.cursor_row].text = line
        self.cursor_col = 0
        self.display_cursor.x = len(self.text_labels[self.cursor_row].text) * self.font_bb[0]
        self.display_cursor.y = self.text_labels[self.cursor_row].y - self.font_bb[1]//2

        if self.lines_written > self.text_rows - 3:
            self.lines_written = 0
            self.print_text(f"Press <Enter> key to continue")
            self.skip_scroll = True # don't move current line for user input
            self.get_input()
            # clear "Press enter" prompt and user entered response...
            self.text_labels[self.cursor_row].text = ""
            self.skip_scroll = True # next output goes where continue prompt was

        #self.print_debug(3,f"add_text_line() done")

    def print_debug(self, level, msg):
        if self.debug >= level :
            print(f"debug:{msg}")

    def print_error(self, error_msg):
        """Print error message on console and screen"""

        print(f"*** ERROR: {error_msg}")
        self.print_text(f"*** ERROR: {error_msg}")
        return
        # future???
        theme = self.THEMES[self.current_theme]
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
        theme = self.THEMES[self.current_theme]

        if self.z_version <= 3:
            # Score/moves format
            status_text = f" {location:<30} Score: {score:>3} Moves: {moves:>3} "
        else:
            # Time format
            status_text = f" {location:<50} {score:>10} "

        # Pad or truncate to exact width
        status_text = status_text[:self.text_cols]  #.ljust(TEXT_COLS)
        status_text += " " * (self.text_cols - len(status_text))
        self.status_label.text = status_text
        self.status_label.text = status_text

    def show_themes(self):
        self.print_text("Available themes:")
        for theme in self.THEMES.keys():
            self.print_text(f"  {theme}")
        #self.print_text("")

    def flush_input_buffer(self):
        while supervisor.runtime.serial_bytes_available:
            sys.stdin.read(1) # clear out any input data before beginning

    def get_input(self):
        """Get input from stdin"""
        start_time = time.monotonic()
        blink_time = time.monotonic()
        self.lines_written = 0
        save_cursor_y = self.display_cursor.y
        user_input = ""
        self.flush_input_buffer()
        while supervisor.runtime.serial_bytes_available:
            sys.stdin.read(1) # clear out any input data before beginning

        done = False
        self.display_cursor.x = len(self.text_labels[self.cursor_row].text) * self.font_bb[0]
        self.display_cursor.y = self.text_labels[self.cursor_row].y - self.font_bb[1]//2
        while True:
            if settings.CURSOR_BLINK and (time.monotonic() - blink_time) > .5:
                # toggle cursor blinking
                blink_time = time.monotonic()
                if self.display_cursor.y < settings.DISPLAY_HEIGHT:
                    save_cursor_y = self.display_cursor.y
                    self.display_cursor.y = settings.DISPLAY_HEIGHT
                else:
                    self.display_cursor.y = save_cursor_y
            time.sleep(0.001)  # Small delay to prevent blocking
            if (time.monotonic() - start_time) > settings.SSTIMEOUT:
                #turn on screen saver
                self.display_saver.y = 0
                # wait for keystroke before turning screen saver off
                sys.stdin.read(1)
                self.display_saver.y=settings.DISPLAY_HEIGHT
                #reset screen saver timer
                start_time = time.monotonic()
            if supervisor.runtime.serial_bytes_available:
                key = sys.stdin.read(1)
                start_time = time.monotonic() # restart screen saver
                if ord(key) == 10:
                    done = True
                elif ord(key) == 8: # backspace
                    if len(user_input) > 0:
                        user_input = user_input[:-1] # remove last character
                        self.text_labels[self.cursor_row].text = self.text_labels[self.cursor_row].text[:-1]
                        self.display_cursor.x = len(self.text_labels[self.cursor_row].text) * self.font_bb[0]
                elif not (32 <= ord(key) and ord(key) <= 126):
                    # non-printable char (function or cursor key perhaps) ignore rest of input
                    self.flush_input_buffer()
                else:
                    user_input += key
                    self.text_labels[self.cursor_row].text += key
                    self.display_cursor.x = len(self.text_labels[self.cursor_row].text) * self.font_bb[0]
                if done:
                    done = False
                    cmd = user_input.strip().lower()
                    if cmd == 'help':
                        self.show_help()
                        self.flush_input_buffer()
                        self.show_input_prompt()
                        user_input = ""
                    elif cmd.startswith('theme '):
                        theme_name = cmd[6:]
                        self.change_theme(theme_name)
                        self.flush_input_buffer()
                        self.show_input_prompt()
                        user_input = ""
                    elif cmd == 'themes':
                        self.show_themes()
                        self.flush_input_buffer()
                        self.show_input_prompt()
                        user_input = ""
                    else:
                        self.print_text("") # scroll 1 line for CR by user
                        #print(f"got user_input '{user_input}'")
                        return user_input

    def does_file_exist(self, filename):
        try:
            status = os.stat(filename)
            file_exists = True
        except OSError:
            file_exists = False
        return file_exists

    def get_save_game_name(self):
        """get filename to save/restore"""
        self.print_text(f"Enter file name ({self.save_game_name}):")
        name = self.get_input().lower().strip()
        if len(name) == 0:
            name = self.save_game_name
        return name

    def restore_game(self):
        """Restore game state"""
        save = self.get_save_game_name()
        save_name = self.filename.split(".")[0].lower() + "." + save
        try:
            save_path = f"{SAVE_DIR}/{save_name}.sav"
            #self.print_debug(3,f"save path: {save_path}")
            if not self.does_file_exist(save_path):
                raise RuntimeError(f"save file not found: {save}")
            # file name exists, ok to save the name
            self.save_game_name = save
            with open(save_path, 'rb') as f:
                # Read header
                magic = f.read(4)
                if magic != b'ZSAV':
                    raise ValueError("Invalid save file")
                version = int.from_bytes(f.read(1))
                if version != self.z_version:
                    raise ValueError("Save file version mismatch")
                self.pc = int.from_bytes(f.read(2), 'big')
                #value = int.from_bytes(f.read(2), 'big')
                #print(f"pc: 0x{self.zm.pc:04x}")

                # Read dynamic memory
                mem_size = int.from_bytes(f.read(2), 'big')
                self.memory[0:mem_size] = f.read(mem_size)
                # Read call stack
                stack_size = int.from_bytes(f.read(2),'big')
                self.call_stack = []

                for i in range(stack_size):
                    frame_size = int.from_bytes(f.read(2), 'big')
                    mem = f.read(frame_size)
                    frame = Frame()
                    frame.unserialize(mem,0)
                    #frame.print(3)
                    self.call_stack.append(frame)
                self.processor.print_frame_stack()

            self.print_text(f"Game restored from {save}")
            #self.zm.pc = self.call_stack[-1].return_pointer
            return True

        except Exception as e:
            self.print_error(f"Restore failed: {e}")
            return False

    def save_game(self):
        """Save game state"""
        save = self.get_save_game_name()
        save_name = self.filename.split(".")[0].lower() + "." + save
        try:
            save_path = f"{SAVE_DIR}/{save_name}.sav"
            #self.print_debug(3,f"save path:{save_path}")
            os.mkdir(SAVE_DIR)
        except Exception as e:
            pass #existing folder?

        try:
            #os.remove(save_path)
            with open(save_path, 'wb') as f:
                # Write header
                f.write(b'ZSAV')  # Magic number
                f.write(self.z_version.to_bytes(1))
                f.write((self.pc).to_bytes(2, 'big'))
                # write dynamic memory
                mem_size = self.read_word(0x0e)
                f.write((mem_size).to_bytes(2, 'big'))
                f.write(self.memory[0:mem_size])

                f.write(len(self.call_stack).to_bytes(2, 'big'))
                for i in range(len(self.call_stack)):
                    frame = self.call_stack[i]
                    data = frame.serialize(0)
                    #frame.print(3)
                    #print(f"frame size: {len(data)}")
                    f.write(len(data).to_bytes(2, 'big'))
                    f.write(data)
            self.print_text(f"Game saved as {save}")
            return True

        except Exception as e:
            self.print_error(f"Save failed: {e}")
            return False

    def restart_game(self):
        try:
            story_path = f"{STORY_DIR}/{self.filename}"
            sp = os.stat(story_path)
            if not sp[0]:
                raise RuntimeError(f"Story file not found: {filename}")
            # Check file size
            stat = os.stat(story_path)
            if stat[6] > MAX_STORY_SIZE:
                raise ValueError(f"Story file too large: {stat[6]} bytes")

            # Read dynamic memory
            with open(story_path, 'rb') as f:
                mem_size = self.read_word(0x0e)
                self.memory[0:mem_size] = f.read(mem_size)
                self.pc = self.read_word(0x06)  # Initial PC
            self.processor.init_frame()
            return True
        except Exception as e:
            self.print_error(f"Restart failed: {e}")
            return False

    def change_theme(self, theme_name):
        """Change color theme"""
        if theme_name in self.THEMES:
            theme = self.THEMES[theme_name]
            self.display_background.fill=theme['bg']
            self.status_label.color=theme['status']
            self.status_label.background_color=theme['status_bg']
            self.display_cursor.fill=theme['text']

            for i in range(len(self.text_labels)):
                self.text_labels[i].color=theme['text']
                self.text_labels[i].background_color=theme['bg']

            self.print_text(f"Theme changed to: {theme_name}\n")
            self.current_theme = theme_name
        else:
            self.print_error(f"Unknown theme: {theme_name}\n")
            return False

    def get_stories(self):
        try:
            files = os.listdir(STORY_DIR)
            story_files = [f for f in files if f.lower().endswith(('.z3', '.z5', '.z8', '.dat'))]
            story_files = sorted(story_files)
            return story_files
        except Exception as e:
            self.print_error(f"Error getting stories: {e}\n")
            return []

    def list_stories(self):
        """List available story files"""
        try:
            story_files = self.get_stories()

            if not story_files:
                self.print_text("No story files found.")
                self.print_text(f"Copy story files to {STORY_DIR}/")
            else:
                self.print_text("Available stories:")
                for i, filename in enumerate(story_files, 1):
                    self.print_text(f"  {i}. {filename}")
            return story_files

        except Exception as e:
            self.print_error(f"Error listing stories: {e}\n")
            return []

    def get_story(self):
        story_files = self.get_stories()
        if len(story_files) == 1:
            # only one story available, no need to prompt for one
            return 1
        self.print_text("Select a story # or enter 0 to exit")
        value = -1
        while value < 0 or value > len(story_files):
            self.show_input_prompt()
            try:
                value = int(self.get_input())
            except ValueError:
                self.print_error(f"Invalid number, try again.")
            if value == 0:
                return 0
            if value < 0 or value > len(story_files):
                self.print_error(f"Invalid input, select between 0 and {len(story_files)}")
        return value

    def run_interpreter(self):
        """Main Z-machine interpreter loop"""
        self.game_running = True
        self.print_text("CPZ Machine: the CircuitPython Z Machine")
        self.print_text("By Dan Cogliano (DanTheGeek.com)")
        self.print_text(f"Display: {self.text_cols} cols x {self.text_rows} rows")
        self.print_text("=" * 50)
        # List available stories
        stories = self.get_stories()
        if not stories:
            return

        # load first story automatically if there is only one
        if stories:
            if len(stories) > 1:
                self.list_stories()
            story = self.get_story()
            if story > 0:
                if self.load_story(stories[story-1]):
                    self.print_text("Game loaded successfully!")
                    self.print_text("Type 'help' for commands")

                    # Start Z-machine execution
                    self.execute_game()

    def execute_game(self):
        """Execute Z-machine instructions"""
        try:
            self.processor.init_frame()
            while self.game_running and self.pc < len(self.memory):
                # Execute one instruction
                if self.processor:
                    self.processor.execute_instruction()

                # Yield control periodically
                if self.processor.instruction_count % 100 == 0:
                    time.sleep(0.001)  # Small delay to prevent blocking
            if not self.game_running :
                self.print_text("Game is no longer running\n")
        except KeyboardInterrupt:
            self.print_text("\nGame interrupted by user")
            self.game_running = False
        except Exception as e:
            self.print_error(f"Game execution error: {e}")
            self.game_running = False

    def show_help(self):
        """Show help information"""
        self.print_text("CPZ Machine Commands:")
        self.print_text("  help     - Show this help")
        self.print_text("  save     - Save current game")
        self.print_text("  restore  - Restore saved game")
        self.print_text("  restart  - Restart game")
        self.print_text("  themes   - List available themes")
        self.print_text("  theme <name> - Change color theme")
        self.print_text("  quit     - Exit CPZ Machine")
        self.print_text("Game commands depend on the loaded story.\n")

# Initialize and run the Z-Machine
def main():
    """Main entry point"""
    print("Starting CPZ Machine for Fruit Jam...")

    zmachine = ZMachine()

    # Initialize display
    if not zmachine.init_display():
        print("Failed to initialize display")
        return

    # Run the interpreter
    zmachine.run_interpreter()

    zmachine.print_text("CPZ Machine terminated")
    print("CPZ Machine terminated")
    zmachine.print_text(f"Press <Enter> key to continue")
    zmachine.get_input()
    supervisor.reload()

if __name__ == "__main__":
    main()
