import discord
from discord.ext import commands
import requests
from PIL import Image
from io import BytesIO
import copy
import asyncio #psure i could just use the sleep() function

#emoji stuff
class SelectionState:
    def __init__(self):
        # First position
        self.letter = None
        self.number = None
        self.position = None
        self.action = None
        # Second position
        self.letter2 = None
        self.number2 = None
        self.position2 = None
        # Flag to track if we're selecting the second position
        self.selecting_second_position = False

class ChessGame:
    def __init__(self, rows=8, columns=8):
        self.board_image = None
        self.pieces = {}  # Format: position -> {"image": img, "type": "token", "piece_minis": []}
        self.empty_board = None
        self.mini_icons = {}  
        self.last_move = None  
        self.rows = rows
        self.columns = columns
        self.notes = ""
        self.selection_states = {}


    
    def save_state(self):
        """Saves current state for undo"""
        self.last_move = copy.deepcopy(self.pieces)  # Only store the current state
    
    def can_undo(self):
        """Checks if there is a move to undo"""
        return self.last_move is not None    

piece_scale = {"factor": 0.9}

games = {}  # Format: {channel_id: ChessGame()}
selection_states = {}
# Add this at the global scope, before your commands
default_board_size = {"rows": 8, "columns": 8}  # Store default/custom size

async def redraw_board(ctx, channel_id): #very important, easy to break
    """Redraws the entire board with all pieces"""
    game = games[channel_id]
    board = game.empty_board.copy()
    
    # Calculate square size based on board dimensions
    square_size_w = board.size[0] // game.columns
    square_size_h = board.size[1] // game.rows
    square_size = min(square_size_w, square_size_h)
    
    # Use global scale factor for piece size
    piece_size = int(square_size * piece_scale["factor"])
    mini_size = int(square_size * 0.3)  # Make mini icons 30% of square size
        
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
        
        x = col * square_size_w
        y = board.size[1] - ((row + 1) * square_size_h)
        
        piece = piece_data["image"].copy()
        piece.thumbnail((piece_size, piece_size), Image.Resampling.LANCZOS)
        
        x_offset = (square_size_w - piece.width) // 2
        y_offset = (square_size_h - piece.height) // 2
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
# Modify your setup_board command to use the custom size
@bot.command(aliases=['setup'])
async def setup_board(ctx, board_url: str = None):
    """Sets up or resets the board with current custom dimensions
    Use that one image in chat or a 600x600 image for best results , or youll probably have to use the resize commands
    """
    channel_id = str(ctx.channel.id)
    
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
        games[channel_id] = ChessGame(rows=rows, columns=columns)
        
        response = requests.get(board_url)
        board_image = Image.open(BytesIO(response.content))
        #board_image = resize_image(board_image)
        games[channel_id].empty_board = board_image
        
        await redraw_board(ctx, channel_id)
        await ctx.send(f"Board setup complete!")
        
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

# stuff for mobile support here- I really should move this to another file
EMOJI_MAPPINGS = {
    "🅰️": "A", "🅱️": "B", "🐱": "C", "🐶": "D", 
    "🥚": "E", "🦊": "F", "🐐": "G", "🐴": "H",
    "1️⃣": "1", "2️⃣": "2", "3️⃣": "3", "4️⃣": "4",
    "5️⃣": "5", "6️⃣": "6", "7️⃣": "7", "8️⃣": "8",
    "❌": "cancel",
    "🏃": "move",
    "🔄": "swap",
    "🔪": "kill"
}

    
async def show_letter_selection(ctx):
    msg = await ctx.send("Select column (A-H):")
    selection_states[str(ctx.channel.id)] = SelectionState()
    
    emojis = ["🅰️", "🅱️", "🐱", "🐶", "🥚", "🦊", "🐐", "🐴", "❌"]
    for emoji in emojis:
        await msg.add_reaction(emoji)

async def show_letter_selection_second(message):
    await message.clear_reactions()
    await message.edit(content=f"Selected {selection_states[str(message.channel.id)].action} from {selection_states[str(message.channel.id)].position}\nSelect destination column (A-H):")
    
    emojis = ["🅰️", "🅱️", "🐱", "🐶", "🥚", "🦊", "🐐", "🐴", "❌"]
    for emoji in emojis:
        await message.add_reaction(emoji)

async def execute_action(message):
    channel_id = str(message.channel.id)
    state = selection_states[channel_id]
    game = games[channel_id]

    if state.action == "move":
        # Execute move_piece
        try:
            game.move_piece(state.position.lower(), state.position2.lower())
            await message.channel.send(f"Moved piece from {state.position} to {state.position2}")
        except Exception as e:
            await message.channel.send(f"Error: {str(e)}")
    elif state.action == "swap":
        # Execute swap_piece
        try:
            game.swap_piece(state.position.lower(), state.position2.lower())
            await message.channel.send(f"Swapped pieces at {state.position} and {state.position2}")
        except Exception as e:
            await message.channel.send(f"Error: {str(e)}")

    # Redraw board and clean up
    await redraw_board(message.channel, channel_id)
    del selection_states[channel_id]
    await message.delete()

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    channel_id = str(reaction.message.channel.id)
    if channel_id not in selection_states:
        return

    emoji = str(reaction.emoji)
    state = selection_states[channel_id]
    
    if emoji not in EMOJI_MAPPINGS:
        return

    value = EMOJI_MAPPINGS[emoji]
    
    if value == "cancel":
        del selection_states[channel_id]
        await reaction.message.delete()
        return

    if state.selecting_second_position:
        # Handle second position selection
        if state.letter2 is None:
            if value in "ABCDEFGH":
                state.letter2 = value
                await show_number_selection(reaction.message)
        elif state.number2 is None:
            if value in "12345678":
                state.number2 = value
                state.position2 = f"{state.letter2}{state.number2}"
                # Execute the move or swap
                await execute_action(reaction.message)
    else:
        # Original position selection
        if state.letter is None:
            if value in "ABCDEFGH":
                state.letter = value
                await show_number_selection(reaction.message)
        elif state.number is None:
            if value in "12345678":
                state.number = value
                state.position = f"{state.letter}{state.number}"
                await show_action_selection(reaction.message)
        elif value in ["move", "swap"]:
            state.action = value
            state.selecting_second_position = True
            await show_letter_selection_second(reaction.message)

async def show_number_selection(message):
    # First clear all existing reactions
    await message.clear_reactions()
    # Add a small delay
    await asyncio.sleep(0.5)  
    
    # Update the message content
    await message.edit(content="Select row (1-8):")
    
    # Add new number emojis
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "❌"]
    for emoji in emojis:
        await message.add_reaction(emoji)


async def show_action_selection(message):
    # First clear all existing reactions
    await message.clear_reactions()
    
    # Update the message content
    await message.edit(content=f"Selected position: {selection_states[str(message.channel.id)].position}\nSelect action:")
    
    # Add action emojis
    await message.add_reaction("🏃")  # move
    await message.add_reaction("🔄")  # swap
    await message.add_reaction("🔪")  # kill
    await message.add_reaction("❌")  # cancel


@bot.command(name='select')
async def start_selection(ctx):
    """testing for emoji support"""
    await show_letter_selection(ctx)

# Run the bot
bot.run('I will set up something i swear')
