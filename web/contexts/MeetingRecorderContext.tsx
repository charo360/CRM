"use client";

import { createContext, useContext, ReactNode } from "react";
import { useMeetingRecorder } from "@/hooks/useMeetingRecorder";

type MeetingRecorderType = ReturnType<typeof useMeetingRecorder>;

const MeetingRecorderContext = createContext<MeetingRecorderType | undefined>(undefined);

export function MeetingRecorderProvider({ children }: { children: ReactNode }) {
  const recorder = useMeetingRecorder();
  return (
    <MeetingRecorderContext.Provider value={recorder}>
      {children}
    </MeetingRecorderContext.Provider>
  );
}

export function useGlobalMeetingRecorder() {
  const context = useContext(MeetingRecorderContext);
  if (context === undefined) {
    throw new Error("useGlobalMeetingRecorder must be used within a MeetingRecorderProvider");
  }
  return context;
}
