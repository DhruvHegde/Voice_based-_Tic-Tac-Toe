import speech_recognition 

def get_player_input():
    recognizer = sr.Recognizer()

    with sr.Microphone() as mic:
        print("Say a move (e.g., 'top left', 'middle center', 'bottom right'): ")
        recognizer.adjust_for_ambient_noise(mic, duration=0.5)
        audio = recognizer.listen(mic)

        try:
            move = recognizer.recognize_google(audio).lower()
            print(f"You said: {move}")
            return move
        except sr.UnknownValueError:
            print("Sorry, I did not understand. Please try again.")
            return get_player_input()
        except Exception as e:
            print(f"Error during audio recognition: {e}")
            print("Please try again.")
            return get_player_input()

def print_board(board):
    for row in board:
        print(" | ".join(row))
        print("-" * 13)

def check_winner(board):
    # Check rows, columns, and diagonals
    for i in range(3):
        if board[i][0] == board[i][1] == board[i][2] != ' ':
            return True
        if board[0][i] == board[1][i] == board[2][i] != ' ':
            return True
    if board[0][0] == board[1][1] == board[2][2] != ' ' or board[0][2] == board[1][1] == board[2][0] != ' ':
        return True
    return False

def is_board_full(board):
    return all(all(cell != ' ' for cell in row) for row in board)

def main():
    board = [[' ' for _ in range(3)] for _ in range(3)]
    player_turn = True  # True for X, False for O

    while True:
        print_board(board)

        if is_board_full(board):
            print("It's a tie!")
            break

        player_marker = 'X' if player_turn else 'O'
        player_input = get_player_input()

        try:
            row, col = {'top': 0, 'middle': 1, 'bottom': 2}[player_input.split()[0]]
            col = {'left': 0, 'center': 1, 'right': 2}[player_input.split()[1]]
        except (KeyError, IndexError):
            print("Invalid move. Please try again.")
            continue

        if board[row][col] == ' ':
            board[row][col] = player_marker
            if check_winner(board):
                print_board(board)
                print(f"Player {player_marker} wins!")
                break
            player_turn = not player_turn
        else:
            print("Invalid move. Cell already taken. Please try again.")

if __name__ == "__main__":
    main()
