# CircuitPython Z-Machine for Adafruit Fruit Jam

A port of the A2Z Machine Z-machine interpreter to CircuitPython with HSTX DVI video output.

## Hardware Requirements

- **Adafruit Fruit Jam** (RP2350B with 16MB Flash + 8MB PSRAM)
- HDMI cable for video output and compatible monitor
- USB keyboard for input
- USB-C cable for programming and power

## Software Requirements

### CircuitPython Version
- CircuitPython 9.2.0 or later (for HSTX DVI support on RP2350)

### Required Libraries
Copy these libraries to the `lib` folder on your CIRCUITPY drive:

```
adafruit_display_text/
adafruit_display_shapes/
adafruit_hid/
```

You can download these from the [CircuitPython Library Bundle](https://circuitpython.org/libraries).

## Installation Steps

### 1. Install CircuitPython
1. Download the latest CircuitPython UF2 file for Fruit Jam from [circuitpython.org](https://circuitpython.org)
2. Hold the BOOT button while plugging in the Fruit Jam
3. Drag the UF2 file to the RPI-RP2 drive
4. The board will restart and show up as CIRCUITPY

### 2. Install Libraries
1. Download the CircuitPython Library Bundle
2. Extract and copy the required libraries to `CIRCUITPY/lib/`:
   - `adafruit_display_text/`
   - `adafruit_display_shapes/`
   - `adafruit_hid/`

### 3. Install Z-Machine Code
1. Copy the main files to the CIRCUITPY drive:
   - `code.py` (main Z-machine implementation)
   - `zmachine_opcodes.py` (opcode processor)

### 4. Create Directory Structure
Create this folder on the CIRCUITPY drive:
```
CIRCUITPY/
└── stories/     # Z-machine game files go here
```

### 5. Add Game Files
Copy Z-machine story files (`.z3`, `.z5`, `.z8`, or `.dat`) to the `stories/` folder.

Popular games you can find online:
- `zork1.z3` - Zork I: The Great Underground Empire
- `zork2.z3` - Zork II: The Wizard of Frobozz  
- `zork3.z3` - Zork III: The Dungeon Master
- `hhgg.z3` - The Hitchhiker's Guide to the Galaxy

## Hardware Connections

### Video Output
- Connect HDMI cable from Fruit Jam's built-in DVI port to your monitor/TV
- Set monitor to appropriate resolution (640x480 recommended)

### Input
- Connect USB keyboard to Fruit Jam's USB-C port using a USB-C hub or adapter
- The keyboard will be automatically detected when the program starts

### Power
- Power via USB-C cable connected to computer or USB power adapter
- The Fruit Jam draws approximately 200-300mA during operation

## Configuration

### Display Settings
Edit the display configuration in `code.py`:

```python
# Display configuration
DISPLAY_WIDTH = 640    # Can be 320 or 640
DISPLAY_HEIGHT = 480   # Can be 240 or 480  
COLOR_DEPTH = 8        # 8-bit for better memory usage
```

### Color Themes
Available themes can be selected by typing `theme <name>` in the game:
- `trs80` - Black background, white text
- `amiga` - Blue background, white text
- `compaq` - Black background, green text
- `lisa` - White background, black text
- `amber` - Black background, amber text

### Memory Settings
The implementation takes advantage of the Fruit Jam's 8MB PSRAM:

```python
MAX_STORY_SIZE = 1024 * 1024  # 1MB max story size
```

## Usage

### Starting the Interpreter
1. Connect hardware as described above
2. Power on the Fruit Jam
3. The Z-machine will start automatically and display available games
4. Use keyboard to navigate and play
5. The game will automatically start if there is only one story file, otherwise it will prompt for it
6. The screen will blank after a period of inactivity (currently 5 minutes), press a key to restore the screen

### Basic Commands
- Type game commands normally (e.g., "look", "north", "take lamp")
- Special interpreter commands:
  - `save` - Save current game
  - `restore` - Restore saved game  
  - `restart` - Restart game  
  - `quit` - Exit interpreter
  - `themes` - List available color themes
  - `theme <name>` - Change color theme
  - `help` - Show help information

Game movement shortcuts:
- `n`, `s`, `e`, `w` - North, South, East, West
- `u`, `d` - Up, Down
- `i` - Inventory
- `l` - Look
- `x` - Examine

## Troubleshooting

### Display Issues
1. **No video output**:
   - Check HDMI cable connection
   - Ensure monitor supports 640x480 resolution
   - Try different HDMI cable
   - Check that CircuitPython 9.2.0+ is installed

2. **Garbled display**:
   - Reduce `COLOR_DEPTH` to 4 or 8
   - Try lower resolution (320x240)
   - Check HDMI cable quality

### Input Issues  
1. **Keyboard not responding**:
   - Check USB connection
   - Try different keyboard
   - Restart the Fruit Jam

2. **Wrong characters**:
   - Check keyboard layout (US keyboard recommended)
   - Some special characters may not be supported

### Game Loading Issues
1. **Game won't load**:
   - Check file is in `stories/` folder
   - Verify file is valid Z-machine format
   - Check file size (must be under 1MB)
   - Ensure sufficient memory available

2. **Corrupted saves**:
   - Saves are stored in `saves/` folder
   - Delete corrupted save files if needed
   - Save files are not compatible between different games

### Memory Issues
1. **Out of memory errors**:
   - Try smaller story files
   - Reduce `COLOR_DEPTH` 
   - Clear old save files
   - Restart interpreter to free memory

## Performance Notes

- The Fruit Jam's RP2350B provides good performance for Z-machine games
- 8MB PSRAM allows loading of large story files entirely into memory
- HSTX DVI output provides crisp, flicker-free video
- Text rendering is optimized for fast scrolling

## File Structure

```
CIRCUITPY/
├── code.py                 # Main Z-machine interpreter
├── zmachine_opcodes.py     # Opcode processor
├── lib/                    # CircuitPython libraries
│   ├── adafruit_display_text/
│   ├── adafruit_display_shapes/
│   └── adafruit_hid/
├── stories/                # Game files (.z3, .z5, .z8)
│   ├── zork1.z3
└── saves/                  # Saved games
```

## Known Limitations

- Not all Z-machine opcodes are fully implemented (sufficient for most games)
- Sound effects not supported (DVI video only, no audio)
- Some advanced Z-machine features may not work
- Limited to Z-machine version 3
- No networking features

## Credits

- Based on the A2Z Machine by Dan Cogliano
- Z-machine specification by Graham Nelson
- Original JZip interpreter by John Holder
- CircuitPython DVI support by Adafruit Industries

## License

This project is open source. Game files may have their own copyright restrictions.

## Getting Help 

For issues specific to this CircuitPython port:
1. Check the troubleshooting section above
2. Verify all hardware connections
3. Ensure you're using compatible CircuitPython version
4. Test with known-good game files

For general Z-machine and interactive fiction help:
- [Interactive Fiction Database](https://ifdb.org/)
- [Interactive Fiction Archive](https://www.ifarchive.org/)
- [Z-machine specification](https://www.inform-fiction.org/zmachine/index.html)
