import sqlite3
import random
import tkinter as tk
from tkinter import filedialog
import shutil
import os
root = tk.Tk()
root.withdraw()

file_path = filedialog.askopenfilename(initialdir = '~/Documents/BloodBowl2/Profiles/ADB831A7FDD83DD1E2A309CE7591DFF8/ManagementLocal',title = "Select Management.db File",filetypes = (("Management File","*.db"),))
BACKUP = file_path + ".bak"
shutil.copyfile(file_path, BACKUP) 
try:
    sqliteConnection = sqlite3.connect(file_path, isolation_level=None)
    cursor = sqliteConnection.cursor()
    print("Successfully Connected to Management.db")
    cursor.execute("SELECT (idTeamListing) FROM bb_player_listing WHERE star != 1 AND IdRaces != 23")
    row = [item[0] for item in cursor.fetchall()]
    cursor.execute("SELECT (ID) FROM bb_player_listing WHERE star != 1 AND IdRaces != 23")
    names = [item[0] for item in cursor.fetchall()]
    shuffled = sorted(row, key=lambda k: random.random())
    print('Randomizing Player Teams')
    for i, n in zip(shuffled, names):
        cursor.execute('''
               UPDATE bb_player_listing
               SET idTeamListing = ?
               WHERE ID = ? AND star != 1 AND IdRaces != 23
               ''', (i,n,))
    res = [] 
    for i in shuffled: 
        if i not in res: 
            res.append(i)
    res.sort()
    for i in(res):
        cursor.execute("SELECT name FROM bb_player_listing WHERE idTeamListing = ?", (i,))
        temp_names = [item[0] for item in cursor.fetchall()]
        cursor.execute("SELECT ID FROM bb_player_listing WHERE idTeamListing = ?", (i,))
        temp_ID = [item[0] for item in cursor.fetchall()]        
        cursor.execute("SELECT idTeamListing FROM bb_player_listing WHERE idTeamListing = ?", (i,))
        temp_idTeamListing = [item[0] for item in cursor.fetchall()]
        playernumber=0 
        for n, x, p in zip(temp_names, temp_idTeamListing, temp_ID):
            playernumber=playernumber+1  
            cursor.execute('''
               UPDATE bb_player_listing
               SET number = ?
               WHERE ID = ? AND star != 1 AND IdRaces != 23
               ''', (playernumber,p,))                
finally:
    if (sqliteConnection):
        sqliteConnection.close()
        print("Randomizing Complete")