import socket

domains = [
    "browserstack.myworkdayjobs.com",
    "browserstack.wd1.myworkdayjobs.com",
    "browserstack.wd3.myworkdayjobs.com",
    "fractal.myworkdayjobs.com",
    "fractal.wd1.myworkdayjobs.com",
    "fractal.wd3.myworkdayjobs.com",
]

for d in domains:
    try:
        ip = socket.gethostbyname(d)
        print(f"YES: {d} -> {ip}")
    except socket.gaierror as e:
        print(f"NO: {d} -> Error: {e}")
