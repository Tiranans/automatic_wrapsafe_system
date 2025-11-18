import cv2
import time
import argparse
from pathlib import Path
import importlib.util

def grab_frame_from_url(url, timeout=10):
    cap = cv2.VideoCapture(url)
    t0 = time.time()
    frame = None
    while time.time() - t0 < timeout:
        ret, f = cap.read()
        if ret and f is not None:
            frame = f
            break
    cap.release()
    return frame

def normalize_roi(x, y, w, h, img_w, img_h):
    nx0 = max(0.0, x / img_w)
    ny0 = max(0.0, y / img_h)
    nx1 = min(1.0, (x + w) / img_w)
    ny1 = min(1.0, (y + h) / img_h)
    return (round(nx0,4), round(ny0,4), round(nx1,4), round(ny1,4))

def load_config_urls(config_path: Path):
    spec = importlib.util.spec_from_file_location("proj_config", str(config_path))
    proj_conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proj_conf)
    m1 = getattr(proj_conf, "MACHINE1_CAMERA_URL", None)
    m2 = getattr(proj_conf, "MACHINE2_CAMERA_URL", None)
    return m1, m2

def main():
    parser = argparse.ArgumentParser(description="Select ROI from RTSP and print normalized ROI (do not modify config.py automatically)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Full RTSP URL to use (overrides --machine)")
    group.add_argument("--machine", type=int, choices=[1,2], help="Use URL from config.py: MACHINE1 or MACHINE2")
    parser.add_argument("--config", help="Path to config.py (used when --machine is set)",
                        default=str(Path(__file__).resolve().parents[1] / "config.py"))
    parser.add_argument("--timeout", type=int, default=12, help="Seconds to wait to grab a frame")
    args = parser.parse_args()

    url = args.url
    if args.machine:
        config_path = Path(args.config)
        if not config_path.exists():
            print("config.py not found at", config_path)
            return
        m1, m2 = load_config_urls(config_path)
        url = m1 if args.machine == 1 else m2
        if url is None:
            print(f"No MACHINE{args.machine}_CAMERA_URL found in {config_path}")
            return

    print("Using URL:", url)
    frame = grab_frame_from_url(url, timeout=args.timeout)
    if frame is None:
        print("Failed to grab a frame from the stream. Check URL and network.")
        return

    h, w = frame.shape[:2]
    # Resize preview if very large
    max_preview = 1200
    scale = 1.0
    if max(w, h) > max_preview:
        scale = max_preview / max(w, h)
        preview = cv2.resize(frame, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
    else:
        preview = frame.copy()

    print("Select ROI on the window. Press ENTER or SPACE to confirm, ESC to cancel.")
    r = cv2.selectROI("Select ROI", preview, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow("Select ROI")
    if r == (0,0,0,0):
        print("No ROI selected. Exiting.")
        return

    rx, ry, rw, rh = r
    # map back to original if scaled
    if scale != 1.0:
        rx = int(rx / scale); ry = int(ry / scale); rw = int(rw / scale); rh = int(rh / scale)

    norm = normalize_roi(rx, ry, rw, rh, w, h)
    machine_tag = f"M{args.machine}" if args.machine else "CUSTOM"
    varname = f"{machine_tag}_DETECT_ROI"
    print("\nNormalized ROI (x0, y0, x1, y1):", norm)
    print(f"\nPaste this into your config.py as:\n{varname} = ({norm[0]}, {norm[1]}, {norm[2]}, {norm[3]})")
    print("\nDone.")

if __name__ == "__main__":
    main()