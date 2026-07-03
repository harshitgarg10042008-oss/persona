import os

try:
    print("START")
    with open("hello.txt", "w") as f:
        f.write("HELLO")
except Exception as e:
    pass
