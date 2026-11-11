import { clsx, type ClassValue } from "clsx";

// Callers combine CSS module classes, which cannot have Tailwind conflicts.
export function cn(...inputs: ClassValue[]) { return clsx(inputs); }
