from tkinter import *
import random
import speech_recognition as sr

# def new_game():
#     global player
#     player = random.choice(players)
#     label.config(text=player + " turn", fg="light blue")
#     for row in range(3):
#         for column in range(3):
#             buttons[row][column].config(text="", bg="#333333", fg="light blue")


# def style_button(button):
#     button["font"] = ('consolas', 20)
#     button["width"] = 5
#     button["height"] = 2
#     button["bg"] = "#666666"
#     button["fg"] = "light blue"

# def empty_spaces():
#     spaces = 9
#     for row in range(3):
#         for column in range(3):
#             if buttons[row][column]['text'] != "":
#                 spaces -= 1
#     return spaces > 0

# def check_winner():
#     for row in range(3):
#         if buttons[row][0]['text'] == buttons[row][1]['text'] == buttons[row][2]['text'] != "":
#             buttons[row][0].config(bg="green")
#             buttons[row][1].config(bg="green")
#             buttons[row][2].config(bg="green")
#             return True
#     for column in range(3):
#         if buttons[0][column]['text'] == buttons[1][column]['text'] == buttons[2][column]['text'] != "":
#             buttons[0][column].config(bg="green")
#             buttons[1][column].config(bg="green")
#             buttons[2][column].config(bg="green")
#             return True
#     if buttons[0][0]['text'] == buttons[1][1]['text'] == buttons[2][2]['text'] != "":
#         buttons[0][0].config(bg="green")
#         buttons[1][1].config(bg="green")
#         buttons[2][2].config(bg="green")
#         return True
#     elif buttons[0][2]['text'] == buttons[1][1]['text'] == buttons[2][0]['text'] != "":
#         buttons[0][2].config(bg="green")
#         buttons[1][1].config(bg="green")
#         buttons[2][0].config(bg="green")
#         return True
#     elif not empty_spaces():
#         for row in range(3):
#             for column in range(3):
#                 buttons[row][column].config(bg="yellow")
#         return "Tie"
#     else:
#         return False

def next_turn(row, column):
    global player
    move = get_player_input()
    if move is not None and buttons[row][column]['text'] == "" and check_winner() is False:
        if make_move(move):
            if check_winner() is False:
                switch_player()
            elif check_winner() is True:
                display_winner_message()
            elif check_winner() == "Tie":
                display_tie_message()

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
            return None
        except sr.RequestError as e:
            print(f"Error with the speech recognition service: {e}")
            print("Please try again.")
            return None

def make_move(move):
    try:
        row, col = {'top': 0, 'middle': 1, 'bottom': 2}[move.split()[0]], {'left': 0, 'centre': 1, 'right': 2}[move.split()[1]]
    except (KeyError, IndexError):
        print("Invalid move. Please try again.")
        return False

    if buttons[row][col]['text'] == "":
        buttons[row][col].config(text=player, fg="blue" if player == "X" else "red")
        print('NEXT ')
        return True
    else:
        print("SPOT ALREADY TAKEN")
        return False

def switch_player():
    global player
    player = players[1] if player == players[0] else players[0]
    label.config(text=(player + " Turn"), fg="light blue")

def display_winner_message():
    label.config(text=(player + " wins"), fg="light blue")

def display_tie_message():
    label.config(text="Tie!", fg="purple")

# GUI Styling
window = Tk()
window.title("Tic-Tac-Toe")
window.configure(bg="#111111")  # Set background color

# Default player value
player = ""

# Label Styling
label = Label(text=player + " Turn", font=('consolas', 24), pady=10, fg="light blue", bg="#111111")
label.pack(side="top")

# Reset Button Styling
reset_button = Button(text="Restart", font=('consolas', 14), command=new_game, bg="gray", fg="brown")
reset_button.pack(side="top", pady=10)

frame = Frame(window, bg="#111111")
frame.pack()

# Button Styling
players = ["X", "O"]
player = random.choice(players)
buttons = [[0, 0, 0],
           [0, 0, 0],
           [0, 0, 0]]

for row in range(3):
    for column in range(3):
        button = Button(frame, text="", command=lambda r=row, c=column: next_turn(r, c))
        style_button(button)
        button.grid(row=row, column=column, padx=5, pady=5)
        buttons[row][column] = button

# Set the initial player's turn
switch_player()

window.mainloop()

# ORC incremental sync smoke test
