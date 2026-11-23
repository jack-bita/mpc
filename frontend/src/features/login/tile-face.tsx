// tile-face.tsx — a worker's face on their PIN tile, from the photo the laptop keeps (PPL-14, 03 §5.13). Never from
// the server, so it shows with no network too: the sync brings the photos down (src/offline/sync/staff-photos.ts), and
// staff-picker.tsx draws a face only for a photo that is here.
//
// The bytes are read here, one photo a tile, not with the tiles' list, which is read again at each change to anyone's
// row: a photo is never changed under its id, so one read is enough, and a change to Juma never blinks Asha's face. Its
// tile names it by its photo (`key`), so a new photo is a new face, never the old one with another address while it
// loads.
//
// The browser shows bytes from an address made for them (URL.createObjectURL), and keeps them in memory for as long as
// the address lives. So it is let go of as the face goes: left, each visit to the tiles would keep every face once
// more, on a laptop that is never closed.
//
// "use client": it reads the laptop's database, in the browser only.
"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import { useShopDatabase } from "@/offline/this-shop";

export function TileFace({
  id,
}: {
  /** The photo, by its id: one that is in the laptop's drawer (staff_photos). */
  id: string;
}) {
  const db = useShopDatabase();
  const [address, setAddress] = useState<string | null>(null);
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    if (db === null) return;
    // The tile went before its photo was read: what comes then is nobody's.
    let gone = false;
    let made: string | null = null;
    db.staff_photos.get(id).then(
      (photo) => {
        // Not there: dropped a moment ago, and the tiles draw themselves again without it.
        if (gone || photo === undefined) return;
        made = URL.createObjectURL(
          new Blob([photo.bytes], { type: photo.content_type }),
        );
        setAddress(made);
      },
      (error: unknown) => {
        // The database refused a read: the names say who it is, and the console why there is no face.
        console.error("a worker's photo was not read", error);
        if (!gone) setBroken(true);
      },
    );
    return () => {
      gone = true;
      if (made !== null) URL.revokeObjectURL(made);
    };
  }, [db, id]);

  // Nothing at all for a photo that can't be opened: a tile with a broken picture says less than one with none.
  if (broken) return null;
  return (
    // Its place is kept from the first moment, so the tiles don't jump as the faces come, a blink after the names.
    <span className="size-28 overflow-hidden rounded-lg">
      {address !== null && (
        <Image
          // Not shrunk by Next.js, which a static app can't: the phone shrank it already (worker-photo.tsx).
          unoptimized
          src={address}
          // Hidden from a screen reader: the name beside it says who it is, and the face would only say it twice.
          alt=""
          width={112}
          height={112}
          // Cut to the square from the top: a phone's photo of a person stands upright, and the head is never at the
          // bottom of it.
          className="size-full object-cover object-top"
          onError={() => setBroken(true)}
        />
      )}
    </span>
  );
}
