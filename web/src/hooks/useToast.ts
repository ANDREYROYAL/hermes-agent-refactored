import { useCallback, useEffect, useRef, useState } from "react";

export function useToast(duration = 3000) {
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const showToast = useCallback(
    (message: string, type: "success" | "error") => {
      setToast({ message, type });
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setToast(null), duration);
    },
    [duration],
  );

  useEffect(() => () => clearTimeout(timerRef.current), []);

  return { toast, showToast };
}
