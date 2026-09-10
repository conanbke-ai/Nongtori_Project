'use client';

import { FormEvent, useEffect, useState } from 'react';
import { translate, type Language } from '@/app/lib/i18n';

type Permissions = {
  viewRevenue: boolean;
  manageMembers: boolean;
  manageFarm: boolean;
  uploadMedia: boolean;
  reviewAlerts: boolean;
  viewHistory: boolean;
};

export type AccountRecord = {
  authenticated: boolean;
  loginId: string | null;
  email: string | null;
  displayName: string | null;
  publicName: string | null;
  accountCode: string | null;
  phone: string | null;
  phoneVerified: boolean;
  notificationsEnabled: boolean;
  preferredLanguage: string;
  role: 'ADMIN' | 'OWNER' | 'WORKER' | null;
  roleLabel: string | null;
  permissions: Permissions;
  loginManagedExternally: boolean;
};

type MemberRow = {
  id: string;
  email: string | null;
  display_name: string | null;
  phone: string | null;
  role: 'ADMIN' | 'OWNER' | 'WORKER';
  role_label: string;
  phone_verified: boolean;
  notifications_enabled: boolean;
  can_manage: boolean;
};

function formatPhone(value: string | null, language: Language) {
  if (!value) return translate(language, 'account.notRegistered');
  if (value.length === 11) return `${value.slice(0, 3)}-${value.slice(3, 7)}-${value.slice(7)}`;
  return value;
}

function nicknameCopy(language: Language) {
  if (language === 'vi') return {
    label: 'Biệt danh',
    hint: 'Biệt danh này hiển thị trong trò chuyện và lịch sử xác nhận. Email đăng nhập không được công khai.',
    placeholder: 'Nhập biệt danh',
  };
  if (language === 'th') return {
    label: 'ชื่อเล่น',
    hint: 'ชื่อเล่นนี้จะแสดงในแชตและประวัติการยืนยัน โดยจะไม่เปิดเผยอีเมลเข้าสู่ระบบ',
    placeholder: 'กรอกชื่อเล่น',
  };
  if (language === 'zh-CN') return {
    label: '昵称',
    hint: '聊天和确认记录会显示此昵称，不会公开登录邮箱。',
    placeholder: '请输入昵称',
  };
  return {
    label: '별명',
    hint: '농장 대화와 확인 기록에는 이 별명이 표시되며, 로그인 이메일은 공개되지 않습니다.',
    placeholder: '사용할 별명을 입력하세요',
  };
}

function editableNickname(value: string | null) {
  const nickname = value?.trim() ?? '';
  return nickname && !nickname.includes('@') ? nickname : '';
}

async function jsonRequest(url: string, init?: RequestInit, errorMessage?: string) {
  const response = await fetch(url, init);
  const result = await response.json() as { error?: string; message?: string; rows?: MemberRow[]; deliveryAvailable?: boolean; challengeId?: string };
  if (!response.ok) throw new Error(errorMessage ?? result.error ?? '요청을 처리하지 못했습니다.');
  return result;
}

export function AccountCenter({
  account,
  farmId,
  language,
  mode = 'profile',
  onChanged,
}: {
  account: AccountRecord;
  farmId: string;
  language: Language;
  mode?: 'profile' | 'members';
  onChanged: () => void;
}) {
  const localizedRole = account.role === 'ADMIN' ? translate(language, 'role.admin')
    : account.role === 'OWNER' ? translate(language, 'role.owner')
      : account.role === 'WORKER' ? translate(language, 'role.worker') : account.roleLabel;
  const nickname = nicknameCopy(language);
  const [displayName, setDisplayName] = useState(editableNickname(account.displayName));
  const [profileMessage, setProfileMessage] = useState('');
  const [profileError, setProfileError] = useState('');
  const [phone, setPhone] = useState(account.phone ?? '');
  const [challengeId, setChallengeId] = useState('');
  const [code, setCode] = useState('');
  const [phoneMessage, setPhoneMessage] = useState('');
  const [phoneError, setPhoneError] = useState('');
  const [smsAvailable, setSmsAvailable] = useState<boolean | null>(null);
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [memberMessage, setMemberMessage] = useState('');
  const [memberError, setMemberError] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<'OWNER' | 'WORKER'>('WORKER');
  const [editingId, setEditingId] = useState('');
  const [editName, setEditName] = useState('');
  const [editRole, setEditRole] = useState<'OWNER' | 'WORKER'>('WORKER');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!farmId || mode !== 'profile') return;
    void jsonRequest(`/api/phone-notifications?farmId=${encodeURIComponent(farmId)}`)
      .then((result) => setSmsAvailable(Boolean(result.deliveryAvailable)))
      .catch(() => setSmsAvailable(false));
  }, [farmId, mode]);

  async function loadMembers() {
    if (!farmId || mode !== 'members' || !account.permissions.manageMembers) return;
    setMembersLoading(true);
    setMemberError('');
    try {
      const result = await jsonRequest(`/api/farm-members?farmId=${encodeURIComponent(farmId)}`);
      setMembers(result.rows ?? []);
    } catch (caught) {
      setMemberError(caught instanceof Error ? caught.message : '사용자 목록을 불러오지 못했습니다.');
    } finally {
      setMembersLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadMembers(), 0);
    return () => window.clearTimeout(timer);
    // farm or permission change is the automatic reload boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [farmId, mode, account.permissions.manageMembers]);

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setSending(true);
    setProfileError('');
    setProfileMessage('');
    try {
      await jsonRequest('/api/account-profile', {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ farmId, displayName, preferredLanguage: language }),
      }, translate(language, 'account.profileSaveFailed'));
      setProfileMessage(translate(language, 'account.profileSaved'));
      onChanged();
    } catch (caught) {
      setProfileError(caught instanceof Error ? caught.message : translate(language, 'account.profileSaveFailed'));
    } finally {
      setSending(false);
    }
  }

  async function requestCode() {
    setSending(true);
    setPhoneError('');
    setPhoneMessage('');
    try {
      const result = await jsonRequest('/api/phone-notifications', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ farmId, action: 'request', phone }),
      }, translate(language, 'account.codeSendFailed'));
      setChallengeId(result.challengeId ?? '');
      setPhoneMessage(translate(language, 'account.codeSent'));
    } catch (caught) {
      setPhoneError(caught instanceof Error ? caught.message : translate(language, 'account.codeSendFailed'));
    } finally {
      setSending(false);
    }
  }

  async function confirmCode() {
    setSending(true);
    setPhoneError('');
    try {
      await jsonRequest('/api/phone-notifications', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ farmId, action: 'confirm', challengeId, code }),
      }, translate(language, 'account.codeVerifyFailed'));
      setPhoneMessage(translate(language, 'account.phoneVerified'));
      setChallengeId('');
      setCode('');
      onChanged();
    } catch (caught) {
      setPhoneError(caught instanceof Error ? caught.message : translate(language, 'account.codeVerifyFailed'));
    } finally {
      setSending(false);
    }
  }

  async function toggleNotifications() {
    setSending(true);
    setPhoneError('');
    try {
      await jsonRequest('/api/phone-notifications', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ farmId, action: 'toggle', enabled: !account.notificationsEnabled }),
      }, translate(language, 'account.notificationSettingFailed'));
      setPhoneMessage(translate(language, 'account.notificationSettingChanged'));
      onChanged();
    } catch (caught) {
      setPhoneError(caught instanceof Error ? caught.message : translate(language, 'account.notificationSettingFailed'));
    } finally {
      setSending(false);
    }
  }

  async function invite(event: FormEvent) {
    event.preventDefault();
    setSending(true);
    setMemberError('');
    setMemberMessage('');
    try {
      const result = await jsonRequest('/api/farm-members', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ farmId, displayName: inviteName, email: inviteEmail, role: inviteRole }),
      });
      setMemberMessage(result.message ?? '사용자를 등록했습니다.');
      setInviteName('');
      setInviteEmail('');
      setInviteRole('WORKER');
      await loadMembers();
    } catch (caught) {
      setMemberError(caught instanceof Error ? caught.message : '사용자를 등록하지 못했습니다.');
    } finally {
      setSending(false);
    }
  }

  async function saveMember(member: MemberRow) {
    setSending(true);
    setMemberError('');
    try {
      const result = await jsonRequest('/api/farm-members', {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ farmId, memberId: member.id, displayName: editName, role: editRole }),
      });
      setMemberMessage(result.message ?? '사용자 정보를 수정했습니다.');
      setEditingId('');
      await loadMembers();
    } catch (caught) {
      setMemberError(caught instanceof Error ? caught.message : '사용자 정보를 수정하지 못했습니다.');
    } finally {
      setSending(false);
    }
  }

  async function removeMember(member: MemberRow) {
    const name = editableNickname(member.display_name) || translate(language, 'members.workerFallback');
    if (!window.confirm(translate(language, 'members.deleteConfirm', { name }))) return;
    setSending(true);
    setMemberError('');
    try {
      const result = await jsonRequest(`/api/farm-members?farmId=${encodeURIComponent(farmId)}&memberId=${encodeURIComponent(member.id)}`, { method: 'DELETE' });
      setMemberMessage(result.message ?? '계정을 삭제했습니다.');
      await loadMembers();
    } catch (caught) {
      setMemberError(caught instanceof Error ? caught.message : '계정을 삭제하지 못했습니다.');
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="account-center">
      {mode === 'profile' && <>
        <section className="account-card account-summary-card">
          <div className="account-role-mark">{localizedRole?.slice(0, 1) ?? '내'}</div>
          <div>
            <span>{translate(language, 'account.role')}</span>
            <h2>{localizedRole ?? '농장 연결 대기'}</h2>
            <p>{translate(language, account.role === 'WORKER' ? 'account.workerDesc' : 'account.ownerDesc')}</p>
          </div>
        </section>

        <div className="account-grid">
          <form className="account-card account-form" onSubmit={saveProfile}>
          <header><span>{translate(language, 'account.myInfo')}</span><h2>{translate(language, 'account.basic')}</h2></header>
          <label><span>{nickname.label}</span><input autoComplete="nickname" maxLength={30} onChange={(event) => setDisplayName(event.target.value)} placeholder={nickname.placeholder} required value={displayName} /></label>
          <p className="account-help">{nickname.hint}</p>
          <label><span>{translate(language, 'account.loginEmail')}</span><input disabled value={account.email ?? '계약 계정 연결 대기'} /></label>
          <p className="account-help">{translate(language, 'account.passwordNotice')}</p>
          {profileMessage && <p className="form-message success">{profileMessage}</p>}
          {profileError && <p className="form-message error">{profileError}</p>}
          <button disabled={sending || !farmId} type="submit">{translate(language, 'account.saveProfile')}</button>
          </form>

          <section className="account-card phone-card">
          <header><span>{translate(language, 'account.miteAlerts')}</span><h2>{translate(language, 'account.phone')}</h2></header>
          <div className="phone-current"><span>{translate(language, 'account.registeredPhone')}</span><strong>{formatPhone(account.phone, language)}</strong><b className={account.phoneVerified ? 'verified' : ''}>{account.phoneVerified ? translate(language, 'account.verified') : translate(language, 'account.verifyNeeded')}</b></div>
          {smsAvailable === false && <p className="service-pending">{translate(language, 'account.smsPending')}</p>}
          <label><span>{account.phoneVerified ? translate(language, 'account.changePhone') : translate(language, 'account.phone')}</span><div><input inputMode="tel" onChange={(event) => setPhone(event.target.value)} placeholder="010-0000-0000" value={phone} /><button disabled={sending || smsAvailable !== true} onClick={() => void requestCode()} type="button">{translate(language, 'account.sendCode')}</button></div></label>
          {challengeId && <label><span>{translate(language, 'account.verificationCode6')}</span><div><input autoComplete="one-time-code" inputMode="numeric" maxLength={6} onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} value={code} /><button disabled={sending || code.length !== 6} onClick={() => void confirmCode()} type="button">{translate(language, 'account.confirm')}</button></div></label>}
          {account.phoneVerified && <button className={`notification-toggle ${account.notificationsEnabled ? 'on' : ''}`} disabled={sending} onClick={() => void toggleNotifications()} type="button"><span>{translate(language, 'account.receiveMite')}</span><b>{account.notificationsEnabled ? translate(language, 'account.notificationsOn') : translate(language, 'account.notificationsOff')}</b></button>}
          {phoneMessage && <p className="form-message success">{phoneMessage}</p>}
          {phoneError && <p className="form-message error">{phoneError}</p>}
          </section>
        </div>
      </>}

      {mode === 'members' && account.permissions.manageMembers && (
        <section className="account-card member-management">
          <header><div><span>{translate(language, 'members.adminOnly')}</span><h2>{translate(language, 'members.title')}</h2><p>{translate(language, 'members.description')}</p></div><b>{translate(language, 'members.people', { count: members.length })}</b></header>
          <form className="member-invite-form" onSubmit={invite}>
            <label><span>{translate(language, 'members.nickname')}</span><input maxLength={80} onChange={(event) => setInviteName(event.target.value)} placeholder={translate(language, 'members.nicknamePlaceholder')} required value={inviteName} /></label>
            <label><span>{translate(language, 'members.loginEmail')}</span><input onChange={(event) => setInviteEmail(event.target.value)} placeholder="worker@example.com" required type="email" value={inviteEmail} /></label>
            {account.role === 'ADMIN' && <label><span>{translate(language, 'members.permission')}</span><select onChange={(event) => setInviteRole(event.target.value as 'OWNER' | 'WORKER')} value={inviteRole}><option value="WORKER">{translate(language, 'role.worker')}</option><option value="OWNER">{translate(language, 'role.owner')}</option></select></label>}
            <button disabled={sending} type="submit">{translate(language, 'members.register')}</button>
          </form>
          <p className="account-help">{translate(language, 'members.inviteHelp')}</p>
          {memberMessage && <p className="form-message success">{memberMessage}</p>}
          {memberError && <p className="form-message error">{memberError}</p>}
          <div className="member-list">
            {membersLoading ? <div className="screen-empty compact"><strong>{translate(language, 'members.loading')}</strong></div> : members.map((member) => (
              <article key={member.id}>
                {editingId === member.id ? (
                  <div className="member-editor">
                    <label><span>{translate(language, 'members.nickname')}</span><input maxLength={80} onChange={(event) => setEditName(event.target.value)} value={editName} /></label>
                    {account.role === 'ADMIN' && <label><span>{translate(language, 'members.permission')}</span><select onChange={(event) => setEditRole(event.target.value as 'OWNER' | 'WORKER')} value={editRole}><option value="WORKER">{translate(language, 'role.worker')}</option><option value="OWNER">{translate(language, 'role.owner')}</option></select></label>}
                    <div><button disabled={sending} onClick={() => void saveMember(member)} type="button">{translate(language, 'common.save')}</button><button onClick={() => setEditingId('')} type="button">{translate(language, 'common.cancel')}</button></div>
                  </div>
                ) : (
                  <>
                    <span className={`member-role ${member.role.toLowerCase()}`}>{member.role_label}</span>
                    <div><strong>{editableNickname(member.display_name) || translate(language, 'members.nicknameMissing')}</strong><p>{member.email}</p></div>
                    <div className="member-notification"><span>{translate(language, member.phone_verified ? 'members.phoneVerified' : 'members.phoneUnverified')}</span><b>{translate(language, member.notifications_enabled ? 'members.smsOn' : 'members.smsOff')}</b></div>
                    {member.can_manage && <div className="member-actions"><button onClick={() => { setEditingId(member.id); setEditName(editableNickname(member.display_name)); setEditRole(member.role === 'OWNER' ? 'OWNER' : 'WORKER'); }} type="button">{translate(language, 'members.edit')}</button><button className="delete" disabled={sending} onClick={() => void removeMember(member)} type="button">{translate(language, 'members.delete')}</button></div>}
                  </>
                )}
              </article>
            ))}
          </div>
          <p className="deletion-note"><strong>{translate(language, 'members.deleteKeepsTitle')}</strong> {translate(language, 'members.deleteKeeps')}</p>
        </section>
      )}
    </div>
  );
}
