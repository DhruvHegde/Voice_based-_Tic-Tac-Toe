from tkinter import *
import random
import speech_recognition as sr

def new_game():
    global player
    player = random.choice(players)
    label.config(text=player + " turn")
    for row in range(3):
        for column in range(3):
            buttons[row][column].config(text="", bg="#F0F0F0")

def empty_spaces():
    spaces = 9
    for row in range(3):
        for column in range(3):
            if buttons[row][column]['text'] != "":
                spaces -= 1
    return spaces > 0

def check_winner():
    for row in range(3):
        if buttons[row][0]['text'] == buttons[row][1]['text'] == buttons[row][2]['text'] != "":
            buttons[row][0].config(bg="green")
            buttons[row][1].config(bg="green")
            buttons[row][2].config(bg="green")
            return True
    for column in range(3):
        if buttons[0][column]['text'] == buttons[1][column]['text'] == buttons[2][column]['text'] != "":
            buttons[0][column].config(bg="light green")
            buttons[1][column].config(bg="light green")
            buttons[2][column].config(bg="light green")
            return True
    if buttons[0][0]['text'] == buttons[1][1]['text'] == buttons[2][2]['text'] != "":
        buttons[0][0].config(bg="light green")
        buttons[1][1].config(bg="light green")
        buttons[2][2].config(bg="light green")
        return True
    elif buttons[0][2]['text'] == buttons[1][1]['text'] == buttons[2][0]['text'] != "":
        buttons[0][2].config(bg="light green")
        buttons[1][1].config(bg="light green")
        buttons[2][0].config(bg="light green")
        return True
    elif not empty_spaces():
        for row in range(3):
            for column in range(3):
                buttons[row][column].config(bg="yellow")
        return "Tie"
    else:
        return False

def next_turn(row, column):
    global player
    move = get_player_input()
    if move is not None and buttons[row][column]['text'] == "" and check_winner() is False:
        make_move(move)
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
        return

    if buttons[row][col]['text'] == "":
        buttons[row][col].config(text=player)
    else:
        print("Invalid move. Cell already taken. Please try again.")


    if buttons[row][col]['text'] == "":
        buttons[row][col].config(text=player)
    else:
        print("Invalid move. Cell already taken. Please try again.")

def switch_player():
    global player
    player = players[1] if player == players[0] else players[0]
    label.config(text=(player + " turn"))

def display_winner_message():
    label.config(text=(player + " wins"))

def display_tie_message():
    label.config(text="Tie!")

window = Tk()
window.title("Tic-Tac-Toe")
players = ["X", "O"]
player = random.choice(players)
buttons = [[0, 0, 0],
           [0, 0, 0],
           [0, 0, 0]]

label = Label(text=player + " turn", font=('consolas', 40))
label.pack(side="top")

reset_button = Button(text="restart", font=('consolas', 20), command=new_game)
reset_button.pack(side="top")

frame = Frame(window)
frame.pack()

for row in range(3):
    for column in range(3):
        button = Button(frame, text="", width=5, height=2,
                        command=lambda r=row, c=column: next_turn(r, c), font=('consolas', 20))
        button.grid(row=row, column=column)
        buttons[row][column] = button

window.mainloop()
