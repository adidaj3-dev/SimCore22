import cv2

def main():
    img = cv2.imread("gspro_capture.png")
    r = cv2.selectROI("Select HUD region", img)
    cv2.destroyAllWindows()

    x, y, w, h = r
    print("\n=== CROP COORDINATES ===")
    print(f"\"x\": {x},")
    print(f"\"y\": {y},")
    print(f"\"width\": {w},")
    print(f"\"height\": {h},")
    print("========================")

if __name__ == "__main__":
    main()
