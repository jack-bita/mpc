// use-camera.test.ts — the laptop's camera (ATT-3, 03 §5.13): on as the screen opens, the ways the browser
// can answer, one photo taken, and its light always off after: after the photo, when the screen closes,
// and when the screen no longer wants it.
//
// The tests' browser (jsdom) has no camera: each test gives the page a pretend one, the browser's answer to
// the page's ask and a track whose `stop()`, the light going off, is watched. The shrinking is
// shrink-photo.test.ts's, so it is a stand-in here.
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { shrinkFrame } from "@/lib/shrink-photo";

import { START_WAIT, useCamera } from "./use-camera";

vi.mock("@/lib/shrink-photo", () => ({ shrinkFrame: vi.fn() }));

/** A camera's track: its light is on until `stop()`; it says "ended" when the camera goes. */
class PretendTrack extends EventTarget {
  stop = vi.fn();
}

/** A pretend camera: the stream the browser hands over, and its one track. */
function aCamera() {
  const track = new PretendTrack();
  const stream = { getTracks: () => [track] } as unknown as MediaStream;
  return { track, stream };
}

/** The page's ask for the camera, answered by `answer`. */
function theBrowserAnswers(answer: () => Promise<MediaStream>) {
  const ask = vi.fn(answer);
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: ask },
    configurable: true,
  });
  return ask;
}

/** An answer that comes only when the test says. */
function later() {
  let give: (stream: MediaStream) => void = () => undefined;
  const answer = new Promise<MediaStream>((resolve) => {
    give = resolve;
  });
  return { answer: () => answer, give };
}

/** The screen's <video>, showing a webcam's 1280 × 720 frame. */
function aVideo() {
  const video = document.createElement("video");
  Object.defineProperty(video, "videoWidth", { value: 1280 });
  Object.defineProperty(video, "videoHeight", { value: 720 });
  return video;
}

/** A JPEG's first bytes: a made-up photo, never a face. */
const PHOTO = new Blob([new Uint8Array([0xff, 0xd8, 0xff])], {
  type: "image/jpeg",
});

afterEach(() => {
  // jsdom's navigator has no camera of its own: the pretend one goes with its test.
  Reflect.deleteProperty(navigator, "mediaDevices");
  vi.mocked(shrinkFrame).mockReset();
  vi.useRealTimers();
});

describe("useCamera", () => {
  it("asks for the front camera as the screen opens, and shows it live", async () => {
    const { stream } = aCamera();
    const ask = theBrowserAnswers(() => Promise.resolve(stream));
    const video = aVideo();

    const { result } = renderHook(() => useCamera(true));
    act(() => result.current.videoRef(video));

    expect(result.current.state).toBe("starting");
    await waitFor(() => expect(result.current.state).toBe("live"));
    // The face, not the room: the front camera, with no sound.
    expect(ask).toHaveBeenCalledWith({
      audio: false,
      video: expect.objectContaining({ facingMode: "user" }) as unknown,
    });
    // The live picture plays in the screen's own <video>.
    expect(video.srcObject).toBe(stream);
  });

  it("asks nothing while the screen doesn't want it", () => {
    const ask = theBrowserAnswers(() => Promise.resolve(aCamera().stream));

    const { result } = renderHook(() => useCamera(false));

    expect(result.current.state).toBe("off");
    expect(ask).not.toHaveBeenCalled();
  });

  it.each([
    // None plugged in, or none that can give a picture.
    ["NotFoundError", "no_camera"],
    ["OverconstrainedError", "no_camera"],
    // Someone pressed Block, or the page may not ask.
    ["NotAllowedError", "blocked"],
    ["SecurityError", "blocked"],
    // Another program holds the camera, or it broke as it started.
    ["NotReadableError", "failed"],
    ["AbortError", "failed"],
  ])("reads the browser's %s as %s", async (refusal, state) => {
    theBrowserAnswers(() => Promise.reject(new DOMException("no", refusal)));

    const { result } = renderHook(() => useCamera(true));

    await waitFor(() => expect(result.current.state).toBe(state));
  });

  it("has no camera on a page the browser gives none", async () => {
    // A page that isn't https or localhost gets no camera at all: no mediaDevices on the navigator.
    const { result } = renderHook(() => useCamera(true));

    await waitFor(() => expect(result.current.state).toBe("no_camera"));
  });

  it("fails when the camera goes while it is live", async () => {
    // Its cable pulled out, say: the track ends by itself.
    const { track, stream } = aCamera();
    theBrowserAnswers(() => Promise.resolve(stream));
    const { result } = renderHook(() => useCamera(true));
    await waitFor(() => expect(result.current.state).toBe("live"));

    act(() => track.dispatchEvent(new Event("ended")));

    expect(result.current.state).toBe("failed");
  });

  it("takes no photo of the frozen frame a camera that went left behind", async () => {
    // The <video> still holds the last frame, and a screen might still show it: the tap is failed, all the
    // same, never a photo of a moment that has passed (ATT-3's review).
    const { track, stream } = aCamera();
    theBrowserAnswers(() => Promise.resolve(stream));
    vi.mocked(shrinkFrame).mockResolvedValue(PHOTO);
    const { result } = renderHook(() => useCamera(true));
    act(() => result.current.videoRef(aVideo()));
    await waitFor(() => expect(result.current.state).toBe("live"));
    act(() => track.dispatchEvent(new Event("ended")));

    let photo: Blob | string = "";
    await act(async () => {
      photo = await result.current.take();
    });

    expect(photo).toBe("failed");
    expect(shrinkFrame).not.toHaveBeenCalled();
  });

  it("turns the light off when the screen closes", async () => {
    const { track, stream } = aCamera();
    theBrowserAnswers(() => Promise.resolve(stream));
    const { result, unmount } = renderHook(() => useCamera(true));
    await waitFor(() => expect(result.current.state).toBe("live"));

    unmount();

    expect(track.stop).toHaveBeenCalled();
  });

  it("turns the light off when the screen no longer wants it", async () => {
    const { track, stream } = aCamera();
    theBrowserAnswers(() => Promise.resolve(stream));
    const { result, rerender } = renderHook(({ on }) => useCamera(on), {
      initialProps: { on: true },
    });
    await waitFor(() => expect(result.current.state).toBe("live"));

    rerender({ on: false });

    expect(track.stop).toHaveBeenCalled();
    expect(result.current.state).toBe("off");
  });

  it("turns off at once a camera that came after the screen closed", async () => {
    // The browser answered late: nobody is left to show it to, so its light must not stay on.
    const { track, stream } = aCamera();
    const { answer, give } = later();
    theBrowserAnswers(answer);
    const { unmount } = renderHook(() => useCamera(true));

    unmount();
    give(stream);

    await waitFor(() => expect(track.stop).toHaveBeenCalled());
  });

  it("takes one shrunk photo of the live frame, then turns the light off", async () => {
    const { track, stream } = aCamera();
    theBrowserAnswers(() => Promise.resolve(stream));
    vi.mocked(shrinkFrame).mockResolvedValue(PHOTO);
    const video = aVideo();
    const { result } = renderHook(() => useCamera(true));
    await waitFor(() => expect(result.current.state).toBe("live"));
    // The <video> may come after the camera: it still gets the live picture.
    act(() => result.current.videoRef(video));
    expect(video.srcObject).toBe(stream);

    let photo: Blob | string = "";
    await act(async () => {
      photo = await result.current.take();
    });

    expect(photo).toBe(PHOTO);
    // The frame as the webcam gives it; shrink-photo.ts brings it down.
    expect(shrinkFrame).toHaveBeenCalledWith(video, 1280, 720);
    expect(track.stop).toHaveBeenCalled();
    expect(result.current.state).toBe("off");
    // A second take, as after a save that failed, finds the camera off: no photo, and no stale frame.
    let again: Blob | string = "";
    await act(async () => {
      again = await result.current.take();
    });
    expect(again).toBe("failed");
    expect(shrinkFrame).toHaveBeenCalledTimes(1);
  });

  it("waits for a camera still starting when she taps", async () => {
    // Asha taps Ingia the moment the screen opens: her photo is taken once the camera comes.
    const { stream } = aCamera();
    const { answer, give } = later();
    theBrowserAnswers(answer);
    vi.mocked(shrinkFrame).mockResolvedValue(PHOTO);
    const { result } = renderHook(() => useCamera(true));
    act(() => result.current.videoRef(aVideo()));

    let taking: Promise<Blob | string> = Promise.resolve("");
    act(() => {
      taking = result.current.take();
    });
    give(stream);

    expect(await taking).toBe(PHOTO);
  });

  it("gives up on a camera that never starts, after 5 seconds", async () => {
    // The browser's question was never answered: the tap goes on without a photo, as failed, and she
    // doesn't wait for good (Jack: A, nobody loses a day to a camera).
    vi.useFakeTimers();
    theBrowserAnswers(later().answer);
    const { result } = renderHook(() => useCamera(true));

    let taking: Promise<Blob | string> = Promise.resolve("");
    act(() => {
      taking = result.current.take();
    });
    await act(() => vi.advanceTimersByTimeAsync(START_WAIT));

    expect(await taking).toBe("failed");
    expect(shrinkFrame).not.toHaveBeenCalled();
  });

  it("has no photo to give when there is no camera, only why", async () => {
    theBrowserAnswers(() =>
      Promise.reject(new DOMException("no", "NotAllowedError")),
    );
    const { result } = renderHook(() => useCamera(true));
    await waitFor(() => expect(result.current.state).toBe("blocked"));

    expect(await result.current.take()).toBe("blocked");
    expect(shrinkFrame).not.toHaveBeenCalled();
  });

  it("fails when the photo can't be made, and still turns the light off", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { track, stream } = aCamera();
    theBrowserAnswers(() => Promise.resolve(stream));
    vi.mocked(shrinkFrame).mockRejectedValue(new Error("can't draw"));
    const { result } = renderHook(() => useCamera(true));
    act(() => result.current.videoRef(aVideo()));
    await waitFor(() => expect(result.current.state).toBe("live"));

    let photo: Blob | string = "";
    await act(async () => {
      photo = await result.current.take();
    });

    expect(photo).toBe("failed");
    expect(track.stop).toHaveBeenCalled();
  });
});
