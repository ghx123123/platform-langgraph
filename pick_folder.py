# 弹系统文件夹选择器, 打印所选绝对路径到 stdout
# 用法: python pick_folder.py [--title ...]
import sys, tkinter as tk
from tkinter import filedialog

title = '选择课程资料文件夹'
if '--title' in sys.argv:
    i = sys.argv.index('--title')
    if i+1 < len(sys.argv): title = sys.argv[i+1]

root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
path = filedialog.askdirectory(title=title)
root.destroy()
print(path if path else '')
