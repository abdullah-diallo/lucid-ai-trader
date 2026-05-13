"use client";

import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";

export function useCurrentUserId(): string {
  const id = useQuery(api.users.currentUserId);
  return id ?? "";
}
