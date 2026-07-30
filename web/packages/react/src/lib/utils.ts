import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind class names, resolving conflicts (the shadcn `cn` helper).
 *
 * @param inputs - Class values (strings, arrays, or conditional objects).
 * @returns The merged class string with later Tailwind utilities winning.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
