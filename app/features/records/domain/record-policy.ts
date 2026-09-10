export type NoteTarget = {
  id: string | null;
  capture_session_id: string;
  frame_id: string | null;
  frame_index: number | null;
  timestamp_ms: number | null;
  track_key: string;
  house_code?: string | null;
  house_name?: string | null;
  bed_code?: string | null;
  bed_name?: string | null;
  zone_code?: string | null;
  zone_name?: string | null;
  video_modality?: string | null;
  location_source?: string | null;
};
export type StoredNoteScope = {
  author_member_id: string | null;
  target_frame_id: string | null;
  evidence_frame_id: string | null;
  parent_note_id: string | null;
  track_key: string;
  status: string;
  language: string;
  content: string;
  updated_at: string;
};


export function belongsToTarget(note: StoredNoteScope, target: NoteTarget) {
  if (target.frame_id) return note.target_frame_id === target.frame_id || note.evidence_frame_id === target.frame_id;
  return !note.target_frame_id && note.track_key === '__SESSION__';
}

