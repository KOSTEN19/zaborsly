import { useEffect, useState } from "react";
import { getToken } from "../api/client";

export function useAuthImage(url: string | null): string | null {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!url) {
      setSrc(null);
      return;
    }

    const token = getToken();
    let objectUrl: string | null = null;

    fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => {
        if (!r.ok) throw new Error("Failed to load image");
        return r.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => setSrc(null));

    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  return src;
}

interface AuthenticatedImageProps {
  url: string | null;
  alt: string;
  className?: string;
}

export default function AuthenticatedImage({ url, alt, className }: AuthenticatedImageProps) {
  const src = useAuthImage(url);

  if (!src) {
    return <div className={`skeleton ${className || "h-48 w-full"}`} />;
  }

  return <img src={src} alt={alt} className={className} />;
}
