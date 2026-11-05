import { findPestTarget, type PestLanguage } from '../domain/catalog';

export type PestCaptureResult =
  | { kind: 'received'; sessionId: string; pestCode: string; refreshFailed: boolean }
  | { kind: 'rejected' }
  | { kind: 'uncertain' };

// Presentation-side HTTP adapter only: no inference, persistence or background retry.
export async function submitPestCapture(body: FormData, {
  send = fetch, onReceived = () => {}, isCurrent = () => true,
}: {
  send?: typeof fetch; onReceived?: () => void | Promise<void>; isCurrent?: () => boolean;
} = {}): Promise<PestCaptureResult> {
  const requestedCode = String(body.get('pestCode') ?? '');
  if (!findPestTarget(requestedCode)) return { kind: 'rejected' };
  let receipt: unknown;
  try {
    const response = await send('/api/pest-capture', { method: 'POST', body });
    // These existing route statuses reject before storing. Generic400/5xx or a
    // lost response cannot prove that a previous write did not commit.
    if ([403, 413, 422].includes(response.status)) return { kind: 'rejected' };
    if (response.status !== 201) return { kind: 'uncertain' };
    receipt = await response.json();
  } catch { return { kind: 'uncertain' }; }
  if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) return { kind: 'uncertain' };
  const value = receipt as Record<string, unknown>;
  if (typeof value.sessionId !== 'string' ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value.sessionId) ||
    value.pestCode !== requestedCode || value.processingStatus !== 'UPLOADED_AWAITING_MODEL') return { kind: 'uncertain' };
  const result: PestCaptureResult = { kind: 'received', sessionId: value.sessionId, pestCode: requestedCode, refreshFailed: false };
  // Read-side refresh cannot turn the established receipt into a failed upload.
  if (isCurrent()) {
    try { await onReceived(); } catch { result.refreshFailed = true; }
  }
  return result;
}

const copy = {
  ko: {
    received: ['사진 접수 완료 · AI 판독 대기', '사진 접수는 진단 완료가 아닙니다. 선택한 병해충 종류는 접수 분류이며, 진단 결과나 방제 처방이 아닙니다.', '필요하면 병해충 관리의 확인 목록에서 위치를 살펴보고 현장에서 관찰한 내용을 기록해 주세요.'],
    rejected: ['사진을 접수하지 못했습니다.', '농장 연결·권한 또는 사진 형식·용량을 확인해야 합니다.', '입력을 확인한 뒤 직접 다시 접수해 주세요.'],
    uncertain: ['사진 접수 결과를 확인할 수 없습니다.', '응답이 불명확해 저장 여부도 아직 알 수 없습니다.', '같은 사진을 다시 보내기 전에 기록을 확인해 주세요. 새로고침으로 이 결과가 자동 복구되지는 않습니다.'],
    refresh: '사진은 접수됐지만 화면 갱신을 완료하지 못했습니다. 재접수하지 말고 화면만 새로 불러와 주세요.',
  },
  vi: {
    received: ['Đã nhận ảnh · Chờ AI phân tích', 'Nhận ảnh không có nghĩa là đã chẩn đoán. Loại sâu bệnh đã chọn chỉ dùng để phân loại hồ sơ, không phải kết luận hay chỉ định xử lý.', 'Nếu cần, xem vị trí trong danh sách kiểm tra sâu bệnh rồi ghi lại điều quan sát được tại chỗ.'],
    rejected: ['Chưa nhận được ảnh.', 'Cần kiểm tra kết nối nông trại, quyền, định dạng hoặc dung lượng ảnh.', 'Kiểm tra dữ liệu rồi chủ động gửi lại.'],
    uncertain: ['Chưa xác nhận được kết quả gửi ảnh.', 'Phản hồi không rõ nên chưa biết ảnh đã được lưu hay chưa.', 'Kiểm tra hồ sơ trước khi gửi lại cùng ảnh. Tải lại trang không tự khôi phục kết quả này.'],
    refresh: 'Ảnh đã được nhận nhưng chưa làm mới màn hình. Chỉ tải lại màn hình, không gửi lại ảnh.',
  },
  th: {
    received: ['รับภาพแล้ว · รอ AI วิเคราะห์', 'การรับภาพไม่ใช่ผลวินิจฉัย ชนิดที่เลือกใช้จัดหมวดบันทึกเท่านั้น ไม่ใช่ข้อสรุปหรือคำแนะนำให้กำจัดศัตรูพืช', 'หากจำเป็น ดูตำแหน่งในรายการตรวจศัตรูพืช แล้วบันทึกสิ่งที่สังเกตได้ในพื้นที่'],
    rejected: ['ยังรับภาพไม่ได้', 'ตรวจการเชื่อมต่อฟาร์ม สิทธิ์ รูปแบบหรือขนาดภาพ', 'ตรวจข้อมูลแล้วส่งใหม่ด้วยตนเอง'],
    uncertain: ['ยังยืนยันผลส่งภาพไม่ได้', 'คำตอบไม่ชัดเจน จึงยังไม่ทราบว่าบันทึกภาพแล้วหรือไม่', 'ตรวจบันทึกก่อนส่งภาพเดิมอีกครั้ง การรีเฟรชไม่กู้คืนผลนี้อัตโนมัติ'],
    refresh: 'รับภาพแล้วแต่รีเฟรชหน้าจอไม่สำเร็จ ให้โหลดหน้าจอใหม่โดยไม่ส่งภาพซ้ำ',
  },
  'zh-CN': {
    received: ['照片已接收 · 等待AI判读', '接收照片不代表完成诊断。所选病虫害仅用于记录分类，不是诊断结果或防治处方。', '如有需要，请在病虫害管理的检查列表中查看位置，并记录现场观察到的情况。'],
    rejected: ['未能接收照片。', '请检查农场连接、权限、照片格式或大小。', '核对输入后再手动提交。'],
    uncertain: ['尚无法确认照片提交结果。', '响应不明确，目前也无法确认是否已保存。', '重新提交同一照片前请先检查记录。刷新页面不会自动恢复此结果。'],
    refresh: '照片已接收，但页面刷新未完成。请仅重新加载页面，不要重复提交照片。',
  },
} satisfies Record<PestLanguage, { received: string[]; rejected: string[]; uncertain: string[]; refresh: string }>;

export function pestCaptureGuidance(result: PestCaptureResult, language: PestLanguage) {
  const [title, reason, action] = copy[language][result.kind];
  return { title, reason, action, refreshWarning: result.kind === 'received' && result.refreshFailed ? copy[language].refresh : null };
}
