"""Entry point of TuringScreenStudio.exe: no arguments = screen app, --settings = settings window."""
import sys


def run():
    if "--settings" in sys.argv:
        import settings
        settings.main()
    else:
        import main
        main.main()


if __name__ == "__main__":
    run()
