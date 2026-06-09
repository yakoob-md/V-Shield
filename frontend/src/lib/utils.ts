import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/**
 * A utility function to merge Tailwind CSS classes safely using clsx and tailwind-merge.
 * This is required for almost all Shadcn components to handle dynamic styling.
 */
export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs))
}
