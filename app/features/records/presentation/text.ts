import type { Language } from '@/app/lib/i18n';
const copy = {
  "ko": {
    "comments": "이 판독 기록의 댓글",
    "commentsHelp": "농장주와 작업자가 이 기록에 댓글과 답글을 남깁니다. 분석 대기 중에도 작성할 수 있습니다.",
    "refresh": "새 댓글 확인"
  },
  "vi": {
    "comments": "Bình luận của bản ghi",
    "commentsHelp": "Chủ trại và nhân viên có thể bình luận, trả lời kể cả khi đang chờ phân tích.",
    "refresh": "Xem bình luận mới"
  },
  "th": {
    "comments": "ความคิดเห็นของบันทึกนี้",
    "commentsHelp": "เจ้าของฟาร์มและคนงานแสดงความคิดเห็นและตอบกลับได้ แม้กำลังรอผลวิเคราะห์",
    "refresh": "ดูความคิดเห็นใหม่"
  },
  "zh-CN": {
    "comments": "该判读记录的评论",
    "commentsHelp": "农场主和工作人员可在此评论和回复，等待分析时也能填写。",
    "refresh": "查看新评论"
  }
} as const;
export function recordText(language: Language, key: keyof typeof copy.ko) { return copy[language][key]; }
