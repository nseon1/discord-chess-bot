import discord # discord
from discord.ext import commands #discord
import requests #discord
from PIL import Image #stuff for the board and images
from io import BytesIO # actually open the cached image created on my pc
import copy # undo button
import asyncio #psure i could just use the sleep() function
import json # for pieces; its like pandas 
import os
from PIL import Image, ImageDraw
from io import BytesIO
from PIL import ImageDraw
import math
from PIL import ImageDraw
from dataclasses import dataclass
from typing import List, Tuple
import math

class ChessGame:
    def __init__(self, rows=8, columns=8, board_type="square"):
        self.board_image = None 
        self.pieces = {}  
        self.empty_board = None
        self.mini_icons = {}  
        self.last_move = None  
        self.rows = rows
        self.columns = columns
        self.notes = ""
        self.board_type = board_type  # New attribute to track board type



    
    def save_state(self):
        """Saves current state for undo"""
        self.last_move = copy.deepcopy(self.pieces)  # Only store the current state
    
    def can_undo(self):
        """Checks if there is a move to undo"""
        return self.last_move is not None #only returns if i can undo    

piece_scale = {"factor": 0.9} # so the square of pieces and square of board arent the exact same size

games = {}  # Format: {channel_id: ChessGame()}
default_board_size = {"rows": 8, "columns": 8}  # Store default/custom size

async def redraw_board(ctx, channel_id): #very important, easy to breakxdc
    """Redraws the entire board with all pieces"""
    game = games[channel_id] # check to  have stuff in its right channel
    board = game.empty_board.copy() #initalize the board
    drawing = ImageDraw.Draw(board)  # Changed variable name to avoid confusion

    
    # Calculate square size based on board dimensions
    square_size_w = board.size[0] // game.columns #get the width of the square size by dividing the board size by the amount of columns (eg: 800px// 10 columns)
    square_size_h = board.size[1] // game.rows # same as above but im psure its [width,height] so array [1] gets the board.height (might be wrong)
    square_size = min(square_size_w, square_size_h) 
    #base dimensions for hex
    width = board.size[0]
    height = board.size[1]

    if game.board_type == "hex":
        hex_width = (width / (game.columns + 0.5))  # Account for offset columns
        hex_size = hex_width / 2  # Size from center to corner
        hex_height = hex_size * 2 * 0.866  # Height of hexagon (√3 * size)
        vertical_spacing = hex_height * 0.75  # Overlap hexagons vertically

    
        def get_hex_center(col, row):
            """Calculate center position for hex grid placement"""
            x = col * (hex_width * 0.75) + hex_size
            y = height - (row * vertical_spacing + hex_size)
            
            # Offset odd columns
            if col % 2:
                y -= vertical_spacing / 2
            
            return int(x), int(y)  # Convert to integers

        def get_hex_points(center_x, center_y):
            """Calculate the six points of a hexagon given its center"""
            points = []
            for i in range(6):
                angle_deg = 60 * i
                angle_rad = math.pi / 180 * angle_deg
                x = center_x + hex_size * math.cos(angle_rad)
                y = center_y + hex_size * math.sin(angle_rad)
                points.append((int(x), int(y)))
            return points
            
        # Draw the hex grid
        grid_color = (100, 100, 100, 128)  # Semi-transparent gray
        for col in range(game.columns):
            for row in range(game.rows):
                center_x, center_y = get_hex_center(col, row)
                hex_points = get_hex_points(center_x, center_y)
                drawing.polygon(hex_points, outline=grid_color, width=1)



    
    # Use global scale factor for piece size
    piece_size = int(hex_size * 1.5 * piece_scale["factor"]) if game.board_type == "hex" else int(square_size * piece_scale["factor"])
    mini_size = int(hex_size * 0.5) if game.board_type == "hex" else int(square_size * 0.3)
        
    # Draw all pieces
    for pos, piece_data in game.pieces.items():
        # Find where the numbers start
        num_start = 0
        while num_start < len(pos) and pos[num_start].isalpha():
            num_start += 1
            
        # Split position into letters and numbers
        col_str = pos[:num_start]
        row = int(pos[num_start:]) - 1
        
        # Convert column letters to index
        col = get_column_index(col_str)

        if game.board_type == "square":
            x = col * square_size_w
            y = board.size[1] - ((row + 1) * square_size_h)

        if game.board_type == "hex":
            x, y = get_hex_center(col, row)
        
        piece = piece_data["image"].copy()
        piece.thumbnail((piece_size, piece_size), Image.Resampling.LANCZOS)
        
        x_offset = (square_size_w - piece.width) // 2
        y_offset = (square_size_h - piece.height) // 2
        x = int(x + x_offset)  # Convert final coordinates to integers
        y = int(y + y_offset)

         # Center the piece in its cell
        if game.board_type == "hex":
            x_offset = -piece.width // 2
            y_offset = -piece.height // 2
            x += x_offset
            y += y_offset
        
        board.paste(piece, (x, y), piece if piece.mode == 'RGBA' else None)
         # Draw piece-specific minis if they exist
        if "piece_minis" in piece_data and piece_data["piece_minis"]:
            mini_list = piece_data["piece_minis"]
            num_icons = len(mini_list)
            
            # Calculate grid layout
            grid_size = int(num_icons ** 0.5) + 1
            mini_size = min(square_size // grid_size, square_size // 3)
            
            for i, mini_data in enumerate(mini_list):
                mini = mini_data["image"].copy()
                mini.thumbnail((mini_size, mini_size), Image.Resampling.LANCZOS)
                
                # Calculate grid position
                grid_x = i % grid_size
                grid_y = i // grid_size
                
                # Position within the square based on grid
                x_offset = (square_size_w - (grid_size * mini_size)) // 2 + (grid_x * mini_size)
                y_offset = (square_size_h - (grid_size * mini_size)) // 2 + (grid_y * mini_size)
                
                board.paste(mini, (x + x_offset, y + y_offset), mini if mini.mode == 'RGBA' else None)
    # Draw all mini icons
    for pos, mini_list in game.mini_icons.items():
        num_icons = len(mini_list)
        
        # Calculate grid layout (try to make it roughly square)
        grid_size = int(num_icons ** 0.5) + 1
        
        # Calculate smaller size based on number of icons
        mini_size = min(square_size // grid_size, square_size // 3)  # No larger than 1/3 square
        
        for i, mini_data in enumerate(mini_list):
            num_start = 0
            while num_start < len(pos) and pos[num_start].isalpha():
                num_start += 1
                
            col_str = pos[:num_start]
            row = int(pos[num_start:]) - 1
            col = get_column_index(col_str)
            
            x = col * square_size_w
            y = board.size[1] - ((row + 1) * square_size_h)
            
            mini = mini_data["image"].copy()
            mini.thumbnail((mini_size, mini_size), Image.Resampling.LANCZOS)
            
            # Calculate grid position
            grid_x = i % grid_size
            grid_y = i // grid_size
            
            # Position within the square based on grid
            x_offset = (square_size_w - (grid_size * mini_size)) // 2 + (grid_x * mini_size)
            y_offset = (square_size_h - (grid_size * mini_size)) // 2 + (grid_y * mini_size)
            x += x_offset
            y += y_offset
            
            board.paste(mini, (x, y), mini if mini.mode == 'RGBA' else None)


    board.save('temp_board.png')
    await ctx.send(file=discord.File('temp_board.png'))
        # Send notes if they exist
    if game.notes:
        await ctx.send(f"{game.notes}")

def validate_position(game, pos: str) -> bool:
    """Validates position format (one or two letters followed by number)"""
    try:
        if len(pos) < 2:
            return False
        
        # Find where the numbers start
        num_start = 0
        while num_start < len(pos) and pos[num_start].isalpha():
            num_start += 1
            if num_start > 2:  # Max 2 letters allowed
                return False
        
        # Check if we have letters followed by numbers
        letters = pos[:num_start]
        numbers = pos[num_start:]
        
        return (len(letters) > 0 and 
                letters.isalpha() and 
                len(numbers) > 0 and 
                numbers.isdigit())
    except:
        return False

def format_position(pos: str) -> str:
    """Formats position to lowercase and strips whitespace"""
    return pos.lower().strip()

def get_column_index(column_str: str) -> int:
    """
    Converts column string to index number
    Example: 'a' -> 0, 'z' -> 25, 'aa' -> 26, 'ab' -> 27, etc.
    """
    result = 0
    for char in column_str:
        result = result * 26 + (ord(char.lower()) - ord('a'))
    return result
    
#bot instance
bot = commands.Bot(command_prefix='.', intents=discord.Intents.all())



@bot.command(aliases=['resize_board'])
async def custom_size(ctx, rows: int, columns: int):
    """
    Changes the board size for future setups.
    Default size is 8x8.
    I think it makes the pieces smaller
    """
    try:
        # Update global default size
        default_board_size["rows"] = rows
        default_board_size["columns"] = columns
        
        await ctx.send(f"Default board size set to {rows}x{columns}! Use .setup_board to create a new board with these dimensions.")
        
    except Exception as e:
        await ctx.send(f"Error setting custom size: {str(e)}")

# setup_board

@bot.command(aliases=['setup'])
async def setup_board(ctx, board_type: str = "square", board_url: str = None):
    """Sets up or resets the board with a chosen type ('square' or 'hex')"""
    channel_id = str(ctx.channel.id)
    
    if board_type.lower() not in ["square", "hex"]:
        await ctx.send("Invalid board type! Use 'square' or 'hex'.")
        return
    
    try:
        if channel_id in games:
            del games[channel_id]
        
        if ctx.message.attachments:
            board_url = ctx.message.attachments[0].url
        if not board_url:
            await ctx.send("Please provide a board image!")
            return
            
        # Use custom size from global default
        rows = default_board_size["rows"]
        columns = default_board_size["columns"]
        games[channel_id] = ChessGame(rows=rows, columns=columns, board_type=board_type.lower())
        
        response = requests.get(board_url)
        board_image = Image.open(BytesIO(response.content))
        games[channel_id].empty_board = board_image
        
        await redraw_board(ctx, channel_id)
        await ctx.send(f"Board setup complete! Type: {board_type.capitalize()}")
        
    except Exception as e:
        await ctx.send(f"Error setting up board: {str(e)}")


def resize_image(image, max_size=None):
    """Resize image while maintaining aspect ratio"""
    ratio = min(max_size / image.width, max_size / image.height)
    if ratio < 1:  # Only resize if image is too large
        new_width = int(image.width * ratio)
        new_height = int(image.height * ratio)
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    return image






@bot.command(aliases= ['scale'])
async def set_scale(ctx, scale: float):

    """
    Adjusts piece scaling (0.1 to 2.0)
    Example: .set_scale 0.7 for 70% size
    """
    try:
        if not (0.1 <= scale <= 2.0):
            await ctx.send("Scale must be between 0.1 (10%) and 2.0 (200%)!")
            return
            
        piece_scale["factor"] = scale
        
        # Redraw board with new scaling if a game exists
        channel_id = str(ctx.channel.id)
        if channel_id in games:
            await redraw_board(ctx, channel_id)
            await ctx.send(f"Piece scale set to {scale*100:.0f}%")
        else:
            await ctx.send(f"Piece scale set to {scale*100:.0f}%. Start a game to see the effect.")
            
    except Exception as e:
        await ctx.send(f"Error setting scale: {str(e)}")

@bot.command(aliases=['reset_game', 'clear_board','clear','reset'])
async def end_game(ctx):
    """Ends the current game and clears the board"""
    channel_id = str(ctx.channel.id)
    try:
        if channel_id in games:
            del games[channel_id]
            await ctx.send("Game ended! All pieces, effects, and notes have been cleared.")
        else:
            await ctx.send("No active game to end!")
            
    except Exception as e:
        await ctx.send(f"Error ending game: {str(e)}")





@bot.command(name='custom_piece')
async def add_custom_piece(ctx, *, args: str):
    """Add a custom chess piece
    Format: !custom_piece PieceName,white_img_url,black_img_url,move_description
    Example: !custom_piece Dragon,https://i.imgur.com/white.png,https://i.imgur.com/black.png,"Moves 3 squares in any direction, can jump pieces"
    """
    try:
        # Split arguments while preserving quoted text
        parts = [p.strip() for p in args.split(',')]
        if len(parts) < 4:
            raise ValueError("Not enough parameters")
            
        # Extract parts with description potentially containing commas
        name, white_img, black_img, *desc_parts = parts
        description = ','.join(desc_parts)  # Rejoin description
        
        # Validate URLs
        if not (white_img.startswith('http') and black_img.startswith('http')):
            raise ValueError("Image URLs must be valid web addresses")
            
        # Add to storage
        success = save_custom_piece(
            name=name,
            white_image=white_img,
            black_image=black_img,
            description=description
        )
        
        if success:
            await ctx.send(f"✅ Successfully added {name} to custom pieces!")
        else:
            await ctx.send(f"⚠️ {name} already exists in custom pieces!")

    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}\n"
                       "**Correct format:** `!custom_piece [name],[white_img],[black_img],[description]`\n"
                       "**Example:** `!custom_piece Dragon,https://i.imgur.com/white.png,https://i.imgur.com/black.png,\"Moves 3 squares any direction\"`")

@bot.command(name='show_piece')
async def show_custom_piece(ctx, piece_name: str):
    """Display information about a custom piece"""
    pieces = load_custom_pieces()
    
    if piece_name in pieces:
        piece = pieces[piece_name]
        embed = discord.Embed(title=f" {piece_name}", description=piece['description'])
        embed.add_field(name="White Image", value=f"[Link]({piece['white_image']})")
        embed.add_field(name="Black Image", value=f"[Link]({piece['black_image']})")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Piece '{piece_name}' not found in custom pieces!")

CUSTOM_PIECES_FILE = 'custom_pieces.json'

def load_custom_pieces():
    """Load custom pieces from JSON file"""
    if os.path.exists(CUSTOM_PIECES_FILE):
        with open(CUSTOM_PIECES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_custom_piece(**piece_data):
    """Save a new custom piece to JSON file"""
    pieces = load_custom_pieces()
    
    if piece_data['name'] in pieces:
        return False
        
    pieces[piece_data['name']] = {
        'white_image': piece_data['white_image'],
        'black_image': piece_data['black_image'],
        'description': piece_data['description']
    }
    
    with open(CUSTOM_PIECES_FILE, 'w') as f:
        json.dump(pieces, f, indent=2)
        
    return True
# piececommands.py (Optional Utilities)

def get_custom_piece(piece_name):
    """Get custom piece data"""
    pieces = load_custom_pieces()
    return pieces.get(piece_name, None)

def format_piece_display(piece_name):
    """Format piece information for display"""
    piece = get_custom_piece(piece_name)
    if piece:
        return (f"**{piece_name}**\n"
                f"{piece['description']}\n"
                f"White: {piece['white_image']}\n"
                f"Black: {piece['black_image']}")
    return "Piece not found"

@bot.command(aliases=['add_white'])
async def add_piece_white(ctx, *, args):
    """Adds a white piece from the custom database to specified positions"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
    
    game = games[channel_id]
    custom_pieces = load_custom_pieces()
    parts = args.split()
    
    # Find all valid piece names in the arguments
    piece_candidates = [p for p in parts if p in custom_pieces]
    
    if len(piece_candidates) != 1:
        await ctx.send(f"❌ Specify exactly one valid piece. Available: {', '.join(custom_pieces.keys())}")
        return
    
    piece_name = piece_candidates[0]
    positions = [p for p in parts if p != piece_name]
    
    # Validate positions
    valid_positions = []
    for pos in positions:
        formatted_pos = format_position(pos)
        if validate_position(game, formatted_pos):
            valid_positions.append(formatted_pos)
        else:
            await ctx.send(f"❌ Invalid position: {pos}")
            return
    
    # Get piece data
    piece_data = custom_pieces.get(piece_name)
    if not piece_data:
        await ctx.send(f"❌ Piece '{piece_name}' not found!")
        return
    
    # Download white image
    try:
        response = requests.get(piece_data['white_image'])
        response.raise_for_status()
        token_img = Image.open(BytesIO(response.content))
    except Exception as e:
        await ctx.send(f"❌ Failed to load image for {piece_name}: {str(e)}")
        return
    
    # Save state and add pieces
    game.save_state()
    for pos in valid_positions:
        game.pieces[pos] = {"image": token_img.copy(), "type": "token"}
    
    await redraw_board(ctx, channel_id)
    await ctx.send(f"✅ Added white {piece_name} to {', '.join(valid_positions).upper()}")

@bot.command(aliases=['add_black'])
async def add_piece_black(ctx, *, args):
    """Adds a black piece from the custom database to specified positions"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
    
    game = games[channel_id]
    custom_pieces = load_custom_pieces()
    parts = args.split()
    
    # Find all valid piece names in the arguments
    piece_candidates = [p for p in parts if p in custom_pieces]
    
    if len(piece_candidates) != 1:
        await ctx.send(f"❌ Specify exactly one valid piece. Available: {', '.join(custom_pieces.keys())}")
        return
    
    piece_name = piece_candidates[0]
    positions = [p for p in parts if p != piece_name]
    
    # Validate positions
    valid_positions = []
    for pos in positions:
        formatted_pos = format_position(pos)
        if validate_position(game, formatted_pos):
            valid_positions.append(formatted_pos)
        else:
            await ctx.send(f"❌ Invalid position: {pos}")
            return
    
    # Get piece data
    piece_data = custom_pieces.get(piece_name)
    if not piece_data:
        await ctx.send(f"❌ Piece '{piece_name}' not found!")
        return
    
    # Download black image
    try:
        response = requests.get(piece_data['black_image'])
        response.raise_for_status()
        token_img = Image.open(BytesIO(response.content))
    except Exception as e:
        await ctx.send(f"❌ Failed to load image for {piece_name}: {str(e)}")
        return
    
    # Save state and add pieces
    game.save_state()
    for pos in valid_positions:
        game.pieces[pos] = {"image": token_img.copy(), "type": "token"}
    
    await redraw_board(ctx, channel_id)
    await ctx.send(f"✅ Added black {piece_name} to {', '.join(valid_positions).upper()}")



# Run the bot


 
#goodies
@bot.command(aliases=['n','note','edit_note','edit'])
async def notes(ctx, *, new_notes=None):
    """
    Display or update game notes.
    Usage: 
    .notes - Display current notes
    .notes <text> - Replace notes with new text
    .notes +<text> - Append text to existing notes
    """
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return

    try:
        game = games[channel_id]
        
        if new_notes is not None:
            if new_notes.startswith('+'):
                game.notes += '\n' + new_notes[1:]
                await ctx.send("Notes appended!")
            else:
                game.notes = new_notes
                await ctx.send("Notes updated!")
            
        notes_display = "```\n"
        if game.notes:
            notes_display += game.notes
        else:
            notes_display += "No notes yet"
        notes_display += "\n```"
        
        await ctx.send(notes_display)
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

@bot.command()
async def undo(ctx):
    """Undoes the last move"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("No chess game in progress!")
        return

    game = games[channel_id]
    if not game.can_undo():
        await ctx.send("No move to undo!")
        return

    try:
        # Restore the previous state
        game.pieces = game.last_move
        game.last_move = None  # Clear the stored state
        
        # Redraw board
        await redraw_board(ctx, channel_id)
        await ctx.send("Move undone!")
        
    except Exception as e:
        await ctx.send(f"Error during undo: {str(e)}")

@bot.command(aliases=['board','show','b'])
async def show_board(ctx):
    """Shows the current board state"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("No active game! Use .setup to start one.")
        return
        
    try:
        await redraw_board(ctx, channel_id)
    except Exception as e:
        await ctx.send(f"Error showing board: {str(e)}")


#piece commands
@bot.command(aliases=['mini'])
async def add_mini(ctx, position: str):
    """Adds a mini icon to a position"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
        
    if not ctx.message.attachments:
        await ctx.send("Please attach an image!")
        return
        
    try:
        game = games[channel_id]
        position = format_position(position)
        
        if not validate_position(game, position):
            await ctx.send(f"Invalid position! Board is {game.columns}x{game.rows}")
            return
            
        attachment = ctx.message.attachments[0]
        response = requests.get(attachment.url)
        mini_icon = Image.open(BytesIO(response.content))
        
        # Initialize list if position doesn't exist
        if position not in game.mini_icons:
            game.mini_icons[position] = []
            
        game.mini_icons[position].append({
            "image": mini_icon,
            "type": "mini"
        })
        
        await redraw_board(ctx, channel_id)
        await ctx.send(f"Added mini icon to {position.upper()} (#{len(game.mini_icons[position])})")
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

@bot.command(aliases=['rmini'])
async def remove_mini(ctx, position: str):
    """Removes a mini icon from a position"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
        
    try:
        game = games[channel_id]
        position = format_position(position)
        
        if position not in game.mini_icons:
            await ctx.send(f"No mini icon at position {position.upper()}!")
            return
            
        del game.mini_icons[position]
        
        await redraw_board(ctx, channel_id)
        await ctx.send(f"Mini icon removed from {position.upper()}")
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

@bot.command(aliases=['add_token','add','a'])
async def add_piece(ctx, *, args):  # Use * to capture all arguments as one string
    """Adds a token to multiple specified positions"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
        
    try:
        game = games[channel_id]
        
        # Split args into positions and URL
        args_split = args.split()
        token_url = args_split[-1] if args_split[-1].startswith('http') else None
        positions = ' '.join(args_split[:-1]) if token_url else ' '.join(args_split)
        
        if ctx.message.attachments:
            token_url = ctx.message.attachments[0].url
        if not token_url:
            await ctx.send("Please provide a token image!")
            return
            
        response = requests.get(token_url)
        token = Image.open(BytesIO(response.content))
        
        # Split and format positions
        position_list = [format_position(pos) for pos in positions.replace(',', ' ').split() if pos.strip()]

        if not position_list:
            await ctx.send("No valid positions provided!")
            return

        # Validate all positions first
        for pos in position_list:
            if not validate_position(game, pos):
                await ctx.send(f"Invalid position: {pos} (Board is {game.columns}x{game.rows})")
                return
            
        # Add pieces to all positions
        for position in position_list:
            game.pieces[position] = {
                "image": token.copy(),
                "type": "token"
            }
        
        await redraw_board(ctx, channel_id)
        await ctx.send(f"Added piece to positions: {', '.join(position_list).upper()}")
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")


@bot.command(aliases=['move_token','move','capture','m']) 
async def move_piece(ctx, from_pos: str = None, to_pos: str = None):
    """Moves a piece from one position to another"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
         
    if from_pos is None or to_pos is None:
        await ctx.send("Usage: `.move [from] [to]`\nExample: `.move A1 B2`")
        return
        
    try:
        game = games[channel_id]
        from_pos = format_position(from_pos)
        to_pos = format_position(to_pos)
        
        if not validate_position(game, from_pos) or not validate_position(game, to_pos):
            await ctx.send(f"Invalid position! Board is {game.columns}x{game.rows}")
            return
            
        game.save_state()
        
        if from_pos not in game.pieces:
            await ctx.send("No piece at that position!")
            return
            
        game.pieces[to_pos] = game.pieces[from_pos]
        del game.pieces[from_pos]
        
        await redraw_board(ctx, channel_id)
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")


@bot.command(aliases=['swap_token','swap','switch','s']) 
async def swap_piece(ctx, pos1: str, pos2: str):
    """Swaps two pieces' positions"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
        
    try:
        game = games[channel_id]
        pos1 = format_position(pos1)
        pos2 = format_position(pos2)
        
        if not validate_position(game, pos1) or not validate_position(game, pos2):
            await ctx.send(f"Invalid position! Board is {game.columns}x{game.rows}")
            return
            
        game.save_state()
        
        if pos1 not in game.pieces:
            await ctx.send(f"No piece at position {pos1.upper()}!")
            return
            
        if pos2 in game.pieces:
            temp_piece = game.pieces[pos2]
            game.pieces[pos2] = game.pieces[pos1]
            game.pieces[pos1] = temp_piece
        else:
            game.pieces[pos2] = game.pieces[pos1]
            del game.pieces[pos1]
        
        await redraw_board(ctx, channel_id)
        await ctx.send(f"Swapped pieces at {pos1.upper()} and {pos2.upper()}")
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")


@bot.command(aliases=['remove_token','delete_piece','remove','delete','del','d'])
async def remove_piece(ctx, position: str):
    """Removes a piece from the specified position"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
        
    try:
        game = games[channel_id]
        position = format_position(position)
        
        if not validate_position(game, position):
            await ctx.send(f"Invalid position! Board is {game.columns}x{game.rows}")
            return
            
        game.save_state()
        
        if position not in game.pieces:
            await ctx.send(f"No piece found at position {position.upper()}!")
            return
            
        del game.pieces[position]
        
        await redraw_board(ctx, channel_id)
        await ctx.send(f"Piece removed from {position.upper()}")
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

@bot.command(aliases=['pmini', 'piece_mini'])
async def add_piece_mini(ctx, position: str):
    """Adds a mini icon to a piece (moves with the piece)"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
        
    if not ctx.message.attachments:
        await ctx.send("Please attach an image!")
        return
        
    try:
        game = games[channel_id]
        position = format_position(position)
        
        if position not in game.pieces:
            await ctx.send("No piece at that position!")
            return
            
        attachment = ctx.message.attachments[0]
        response = requests.get(attachment.url)
        mini_icon = Image.open(BytesIO(response.content))
        
        # Initialize piece_minis list if it doesn't exist
        if "piece_minis" not in game.pieces[position]:
            game.pieces[position]["piece_minis"] = []
            
        game.pieces[position]["piece_minis"].append({
            "image": mini_icon,
            "type": "mini"
        })
        
        await redraw_board(ctx, channel_id)
        await ctx.send(f"Added mini icon to piece at {position.upper()} (#{len(game.pieces[position]['piece_minis'])})")
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

@bot.command(aliases=['rpmini',])
async def remove_piece_mini(ctx, position: str, index: int = None):
    """Removes a mini icon from a piece"""
    channel_id = str(ctx.channel.id)
    if channel_id not in games:
        await ctx.send("Please setup a board first!")
        return
        
    try:
        game = games[channel_id]
        position = format_position(position)
        
        if position not in game.pieces:
            await ctx.send("No piece at that position!")
            return
            
        if "piece_minis" not in game.pieces[position] or not game.pieces[position]["piece_minis"]:
            await ctx.send("This piece has no mini icons!")
            return
            
        if index is None:
            # Remove all piece minis
            game.pieces[position]["piece_minis"] = []
            await ctx.send(f"Removed all mini icons from piece at {position.upper()}")
        else:
            # Remove specific mini
            idx = index - 1
            if 0 <= idx < len(game.pieces[position]["piece_minis"]):
                game.pieces[position]["piece_minis"].pop(idx)
                await ctx.send(f"Removed mini icon #{index} from piece at {position.upper()}")
            else:
                await ctx.send(f"Invalid mini icon number! Piece has {len(game.pieces[position]['piece_minis'])} icons.")
        
        await redraw_board(ctx, channel_id)
        
    except Exception as e:
        await ctx.send(f"Error: {str(e)}")

#almost certain below is not going to work.



bot.run('a.a.a')
