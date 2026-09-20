from PIL import ImageGrab
import time

def main():
    print("Capturing screenshot in 3 seconds...")
    time.sleep(3)
    img = ImageGrab.grab()
    img.save("gspro_capture.png")
    print("Saved as gspro_capture.png")

if __name__ == "__main__":
    main()
