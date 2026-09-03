import getpass

from argon2 import PasswordHasher


def main() -> None:
    password = getpass.getpass("管理员密码：")
    confirmation = getpass.getpass("再次输入：")
    if not password or password != confirmation:
        raise SystemExit("两次密码不一致或密码为空。")
    print(PasswordHasher().hash(password))


if __name__ == "__main__":
    main()
