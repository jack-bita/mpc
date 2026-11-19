// use-camera.ts — the laptop's camera, for a screen that takes a photo (ATT-3, 03 §5.13): it turns the
// camera on while the screen wants it, shows the live picture in the screen's <video>, takes one photo,
// shrunk, and always turns the camera off again. It owns asking the browser, reading its answer, and the
// camera's light: off after the photo, when the screen closes, and when the screen no longer wants it, so
// the light never stays on over an empty counter.
//
// The page asks the browser (getUserMedia), and the browser asks the person once per site: the manager
// says Allow as the laptop is set up, and nobody is asked again. Its answer is one of five states:
//   starting   asked, no answer yet
//   live       the camera is on, its picture in the <video>
//   no_camera  none plugged in, none that gives a picture, or a page the browser gives no camera at all
//              (only https and localhost may ask)
//   blocked    someone pressed Block, or the page may not ask
//   failed     another program holds it, it broke as it started, or it went while live
// The last three are the server's own reasons for a tap with no photo (NoPhoto, apps/staffpay/models.py):
// a camera that can't is never a reason to refuse a tap (Jack, ATT-3: A), so the screen sends the reason.
//
// Written to React's rules for effects: no state is set in an effect's own body, only in the browser's
// answers, and a change of `on` resets what was found while the screen draws (React's "adjust state when a
// prop changes"), so a camera turned on again starts again from "starting".
import { useCallback, useEffect, useRef, useState } from "react";

import { shrinkFrame } from "@/lib/shrink-photo";

/** Why there is no photo: the server's reasons, as the clock document's `no_photo` sends them. */
export type CameraProblem = "no_camera" | "blocked" | "failed";

export type CameraState = "off" | "starting" | "live" | CameraProblem;

export interface Camera {
  state: CameraState;
  /** For the screen's <video>, which shows the live picture: `<video ref={camera.videoRef} />`. */
  videoRef: (video: HTMLVideoElement | null) => void;
  /** Takes one photo of the live picture, shrunk to about 150 KB, and turns the camera off. With no
   * photo to take, why: the camera's problem, or `failed` when the photo couldn't be made. */
  take: () => Promise<Blob | CameraProblem>;
}

/** How long a tap waits for a camera still starting, or for its first frame: then it goes on without. */
export const START_WAIT = 5 * 1000;

// The front camera, the face's, not the room's (laptops have only that one; the shop's phone has two). An
// ideal of 1280 × 720, which most webcams give: bigger only costs bytes, shrink-photo.ts brings it to
// 1,600 px at most anyway. No sound.
const ASK: MediaStreamConstraints = {
  audio: false,
  video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
};

// What the browser's answer came to: live, a problem, or off once the photo was taken.
type Found = "live" | CameraProblem | "off";

export function useCamera(on: boolean): Camera {
  const [found, setFound] = useState<Found | null>(null);
  const [wasOn, setWasOn] = useState(on);
  if (on !== wasOn) {
    setWasOn(on);
    setFound(null);
  }
  const state: CameraState = on ? (found ?? "starting") : "off";

  const stream = useRef<MediaStream | null>(null);
  const video = useRef<HTMLVideoElement | null>(null);
  // Settles once the camera is live or can't be: what a tap waits for. Off until the camera is asked for.
  const outcome = useRef<Promise<Found>>(Promise.resolve("off"));

  // The live picture into the <video>, whichever of the two comes first. The <video> plays it by itself:
  // the screen gives it autoPlay and muted, which a browser plays with no tap.
  const show = useCallback(() => {
    const element = video.current;
    if (element !== null && element.srcObject !== stream.current)
      element.srcObject = stream.current;
  }, []);

  // The light off: every track stopped, and the <video> emptied.
  const stop = useCallback(() => {
    for (const track of stream.current?.getTracks() ?? []) track.stop();
    stream.current = null;
    show();
  }, [show]);

  useEffect(() => {
    if (!on) return;
    // Gone: the screen closed, or no longer wants the camera, before the browser answered.
    let gone = false;
    let settle: (result: Found) => void = () => undefined;
    outcome.current = new Promise((resolve) => {
      settle = (result) => {
        resolve(result);
        if (!gone) setFound(result);
      };
    });
    // A page with no camera at all (not https, nor localhost) has no mediaDevices: asked the same way, so
    // its answer comes as every other does, as no camera.
    const devices: MediaDevices | undefined = navigator.mediaDevices;
    const asked = devices
      ? devices.getUserMedia(ASK)
      : Promise.reject(new DOMException("No camera here.", "NotFoundError"));
    asked.then(
      (given) => {
        if (gone) {
          // Nobody is left to show it to: its light goes off at once.
          for (const track of given.getTracks()) track.stop();
          return;
        }
        stream.current = given;
        show();
        // A camera that goes while live (its cable pulled out): the next tap has no photo, as failed.
        for (const track of given.getTracks())
          track.addEventListener("ended", () => {
            if (!gone) setFound("failed");
          });
        settle("live");
      },
      (refusal: unknown) => settle(problemOf(refusal)),
    );
    return () => {
      gone = true;
      stop();
    };
  }, [on, show, stop]);

  const videoRef = useCallback(
    (element: HTMLVideoElement | null) => {
      video.current = element;
      show();
    },
    [show],
  );

  const take = useCallback(async (): Promise<Blob | CameraProblem> => {
    try {
      const result = await within(outcome.current, START_WAIT, "failed");
      if (result === "off") return "failed";
      if (result !== "live") return result;
      const element = video.current;
      if (element === null || !(await hasAFrame(element))) return "failed";
      return await shrinkFrame(
        element,
        element.videoWidth,
        element.videoHeight,
      );
    } catch (error) {
      // A browser that couldn't draw or save the frame: a bug or a broken camera, never her fault. The
      // tap goes on without a photo, as failed, and the console says why, for whoever looks.
      console.error("the camera's photo was not taken", error);
      return "failed";
    } finally {
      // The photo is taken, or never will be: the light goes off now, not when the screen closes.
      stop();
      setFound("off");
    }
  }, [stop]);

  return { state, videoRef, take };
}

// The browser's refusal, as one of the camera's problems. By the error's name, which every browser gives
// (a DOMException's): NotFoundError for no camera, NotAllowedError for Block, and so on. Read from any
// object, never by `instanceof`: an error made in another window (a frame's, or the tests' jsdom) is no
// instance of this one's Object or Error, yet has its name all the same.
function problemOf(refusal: unknown): CameraProblem {
  const name =
    typeof refusal === "object" && refusal !== null && "name" in refusal
      ? refusal.name
      : undefined;
  if (name === "NotFoundError" || name === "OverconstrainedError")
    return "no_camera";
  if (name === "NotAllowedError" || name === "SecurityError") return "blocked";
  return "failed";
}

// The answer, or `otherwise` once `wait` milliseconds have passed, whichever comes first.
function within<T>(answer: Promise<T>, wait: number, otherwise: T): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<T>((resolve) => {
    timer = setTimeout(() => resolve(otherwise), wait);
  });
  return Promise.race([answer, late]).finally(() => clearTimeout(timer));
}

// Whether the <video> has a frame to draw: a camera just turned on may not have sent its first one, whose
// size is still 0 × 0. Waits for it, as long as a camera's start.
async function hasAFrame(element: HTMLVideoElement): Promise<boolean> {
  if (element.videoWidth > 0) return true;
  const first = new Promise<boolean>((resolve) => {
    element.addEventListener("loadeddata", () => resolve(true), { once: true });
  });
  return within(first, START_WAIT, false);
}
