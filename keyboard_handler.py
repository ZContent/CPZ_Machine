"""
Keyboard Input Handler for CircuitPython Z-Machine
Handles USB keyboard input for text adventure games

This module provides keyboard input functionality that replaces
the serial input used in the original A2Z Machine.
"""

import usb_hid
import time
import sys
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

class ZKeyboardHandler:
    def __init__(self, zmachine):
        self.zm = zmachine
        self.keyboard = None
        self.input_buffer = ""
        self.history = []
        self.history_index = -1
        self.cursor_pos = 0
        self.prompt = "> "
        self.prompt = "" # use prompt from Z machine
        self.max_input_length = 80

        # Key mapping for special characters
        self.key_map = {
            Keycode.SPACE: ' ',
            Keycode.PERIOD: '.',
            Keycode.COMMA: ',',
            Keycode.SEMICOLON: ';',
            Keycode.QUOTE: "'",
            Keycode.ENTER: '\n',
            Keycode.TAB: '\t',
        }

        # Shifted key mappings
        self.shifted_keys = {
            Keycode.ONE: '!',
            Keycode.TWO: '@',
            Keycode.THREE: '#',
            Keycode.FOUR: '$',
            Keycode.FIVE: '%',
            Keycode.SIX: '^',
            Keycode.SEVEN: '&',
            Keycode.EIGHT: '*',
            Keycode.NINE: '(',
            Keycode.ZERO: ')',
            Keycode.MINUS: '_',
            Keycode.EQUALS: '+',
            Keycode.LEFT_BRACKET: '{',
            Keycode.RIGHT_BRACKET: '}',
            Keycode.BACKSLASH: '|',
            Keycode.SEMICOLON: ':',
            Keycode.QUOTE: '"',
            Keycode.GRAVE_ACCENT: '~',
            Keycode.COMMA: '<',
            Keycode.PERIOD: '>',
            Keycode.FORWARD_SLASH: '?',
        }

        self.init_keyboard()

    def init_keyboard(self):
        """Initialize USB keyboard"""
        try:
            self.keyboard = Keyboard(usb_hid.devices)
            print("USB keyboard initialized for input")
            return True
        except Exception as e:
            print(f"Failed to initialize keyboard: {e}")
            return False

    def show_input_prompt(self):
        """Display input prompt"""
        theme = self.zm.THEMES[self.zm.current_theme]

        # Show prompt on current line
        prompt_text = self.prompt + self.input_buffer
        if self.zm.cursor_row < len(self.zm.text_labels):
            # Change color to input color
            self.zm.text_labels[self.zm.cursor_row].color = theme['input']
            self.zm.text_labels[self.zm.cursor_row].text = prompt_text + "_"  # Show cursor

    def handle_keypress(self, keycode, shift_pressed=False):
        """Handle individual keypress"""
        # Handle special keys
        if keycode == Keycode.ENTER:
            return self.handle_enter()
        elif keycode == Keycode.BACKSPACE:
            return self.handle_backspace()
        elif keycode == Keycode.DELETE:
            return self.handle_delete()
        elif keycode == Keycode.LEFT_ARROW:
            return self.handle_left_arrow()
        elif keycode == Keycode.RIGHT_ARROW:
            return self.handle_right_arrow()
        elif keycode == Keycode.UP_ARROW:
            return self.handle_up_arrow()
        elif keycode == Keycode.DOWN_ARROW:
            return self.handle_down_arrow()
        elif keycode == Keycode.HOME:
            self.cursor_pos = 0
            return None
        elif keycode == Keycode.END:
            self.cursor_pos = len(self.input_buffer)
            return None
        elif keycode == Keycode.ESCAPE:
            self.input_buffer = ""
            self.cursor_pos = 0
            return None

        # Handle printable characters
        char = self.keycode_to_char(keycode, shift_pressed)
        if char and len(self.input_buffer) < self.max_input_length:
            # Insert character at cursor position
            self.input_buffer = (self.input_buffer[:self.cursor_pos] +
                               char +
                               self.input_buffer[self.cursor_pos:])
            self.cursor_pos += 1

        return None

    def keycode_to_char(self, keycode, shift_pressed):
        """Convert keycode to character"""
        # Handle letters
        if Keycode.A <= keycode <= Keycode.Z:
            char = chr(ord('A') + keycode - Keycode.A)
            return char if shift_pressed else char.lower()

        # Handle numbers
        if Keycode.ZERO <= keycode <= Keycode.NINE:
            if shift_pressed and keycode in self.shifted_keys:
                return self.shifted_keys[keycode]
            return chr(ord('0') + keycode - Keycode.ZERO)

        # Handle special characters
        if keycode in self.key_map:
            if shift_pressed and keycode in self.shifted_keys:
                return self.shifted_keys[keycode]
            return self.key_map[keycode]

        # Handle other shifted characters
        if shift_pressed and keycode in self.shifted_keys:
            return self.shifted_keys[keycode]

        return None

    def handle_enter(self):
        """Handle enter key - submit input"""
        if self.input_buffer.strip():
            # Add to history
            self.history.append(self.input_buffer)
            if len(self.history) > 50:  # Limit history size
                self.history.pop(0)

            result = self.input_buffer.strip()
            self.input_buffer = ""
            self.cursor_pos = 0
            self.history_index = -1

            # Move to next line
            self.zm.cursor_row += 1

            return result

        return None

    def handle_backspace(self):
        """Handle backspace key"""
        if self.cursor_pos > 0:
            self.input_buffer = (self.input_buffer[:self.cursor_pos-1] +
                               self.input_buffer[self.cursor_pos:])
            self.cursor_pos -= 1
        return None

    def handle_delete(self):
        """Handle delete key"""
        if self.cursor_pos < len(self.input_buffer):
            self.input_buffer = (self.input_buffer[:self.cursor_pos] +
                               self.input_buffer[self.cursor_pos+1:])
        return None

    def handle_left_arrow(self):
        """Handle left arrow key"""
        if self.cursor_pos > 0:
            self.cursor_pos -= 1
        return None

    def handle_right_arrow(self):
        """Handle right arrow key"""
        if self.cursor_pos < len(self.input_buffer):
            self.cursor_pos += 1
        return None

    def handle_up_arrow(self):
        """Handle up arrow key - previous history"""
        if self.history:
            if self.history_index == -1:
                self.history_index = len(self.history) - 1
            elif self.history_index > 0:
                self.history_index -= 1

            if 0 <= self.history_index < len(self.history):
                self.input_buffer = self.history[self.history_index]
                self.cursor_pos = len(self.input_buffer)

        return None

    def handle_down_arrow(self):
        """Handle down arrow key - next history"""
        if self.history and self.history_index != -1:
            if self.history_index < len(self.history) - 1:
                self.history_index += 1
                self.input_buffer = self.history[self.history_index]
            else:
                self.history_index = -1
                self.input_buffer = ""

            self.cursor_pos = len(self.input_buffer)

        return None

    def get_input_line(self, timeout=None):
        """Get a complete line of input from keyboard

        Args:
            timeout: Maximum time to wait in seconds (None for no timeout)

        Returns:
            String input or None if timeout
        """
        self.show_input_prompt()
        start_time = time.monotonic()

        while True:
            # Check for timeout
            if timeout and (time.monotonic() - start_time) > timeout:
                return None

            # In a real implementation, this would check for actual key events
            # For now, we'll simulate with a simplified approach
            try:
                # This is a placeholder - real implementation would need
                # proper USB HID event handling
                user_input = ""
                while True:
                    key = sys.stdin.read(1)
                    print(ord(key))
                    if ord(key) == 10:
                        break
                    if ord(key) == 8: # backspace
                        user_input = user_input[:-1] # remove last character
                    else:
                        user_input += key

                #user_input = input(self.prompt).strip()

                if user_input:
                    self.history.append(user_input)
                    if len(self.history) > 50:
                        self.history.pop(0)

                return user_input

            except KeyboardInterrupt:
                return "quit"
            except Exception as e:
                print(f"Input error: {e}")
                time.sleep(0.1)

    def clear_input(self):
        """Clear current input buffer"""
        self.input_buffer = ""
        self.cursor_pos = 0

    def set_prompt(self, prompt):
        """Set input prompt text"""
        self.prompt = prompt

    def add_to_history(self, command):
        """Add command to history"""
        if command.strip() and (not self.history or self.history[-1] != command):
            self.history.append(command)
            if len(self.history) > 50:
                self.history.pop(0)

    def get_history(self):
        """Get command history"""
        return self.history.copy()

    def clear_history(self):
        """Clear command history"""
        self.history.clear()
        self.history_index = -1

# Helper functions for keyboard handling
def is_printable_key(keycode):
    """Check if keycode represents a printable character"""
    return (Keycode.A <= keycode <= Keycode.Z or
            Keycode.ZERO <= keycode <= Keycode.NINE or
            keycode in [Keycode.SPACE, Keycode.PERIOD, Keycode.COMMA,
                       Keycode.SEMICOLON, Keycode.QUOTE, Keycode.MINUS,
                       Keycode.EQUALS, Keycode.LEFT_BRACKET, Keycode.RIGHT_BRACKET,
                       Keycode.BACKSLASH, Keycode.GRAVE_ACCENT, Keycode.FORWARD_SLASH])

def get_key_combinations():
    """Get help text for key combinations"""
    return """
Keyboard Commands:
  Enter       - Submit command
  Backspace   - Delete character left
  Delete      - Delete character right
  Left/Right  - Move cursor
  Up/Down     - Command history
  Home        - Move to start of line
  End         - Move to end of line
  Escape      - Clear current input
  Ctrl+C      - Quit game
"""

# Special game command shortcuts
GAME_SHORTCUTS = {
    'n': 'north',
    's': 'south',
    'e': 'east',
    'w': 'west',
    'ne': 'northeast',
    'nw': 'northwest',
    'se': 'southeast',
    'sw': 'southwest',
    'u': 'up',
    'd': 'down',
    'i': 'inventory',
    'l': 'look',
    'x': 'examine',
    'g': 'again',
    'z': 'wait',
}

def expand_shortcuts(command):
    """Expand common game shortcuts"""
    words = command.lower().split()
    if words and words[0] in GAME_SHORTCUTS:
        words[0] = GAME_SHORTCUTS[words[0]]
        return ' '.join(words)
    return command
