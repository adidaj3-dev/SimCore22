# mvp/tools/gspro_hud_autocrop_helper.py

import cv2


def main():
    img = cv2.imread("gspro_capture.png")
    if img is None:
        print("Could not find gspro_capture.png. Run capture_screenshot.py first.")
        return

    h, w, _ = img.shape
    print(f"Image size: {w}x{h}")

    # Example: paste your current crop here to visualize it
    x = int(input("Enter HUD x: "))
    y = int(input("Enter HUD y: "))
    cw = int(input("Enter HUD width: "))
    ch = int(input("Enter HUD height: "))

    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + cw, y + ch), (0, 255, 0), 2)

    alpha = 0.4
    blended = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)

    cv2.imshow("HUD Crop Overlay", blended)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
