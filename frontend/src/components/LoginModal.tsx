import React, { useState } from 'react';
import toast from 'react-hot-toast';

import { login } from '../services/api';

interface LoginModalProps {
  open: boolean;
  // Called after a successful sign-in (the token is already stored).
  onSuccess: () => void;
}

const LoginModal: React.FC<LoginModalProps> = ({ open, onSuccess }) => {
  const [form, setForm] = useState({ username: '', password: '' });

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await login(form.username, form.password);
    if (result.success) {
      setForm({ username: '', password: '' });
      toast.success('Signed in');
      onSuccess();
    } else {
      toast.error(result.error || 'Sign-in failed');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm space-y-4"
      >
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Sign in</h2>
          <p className="text-sm text-gray-600">Clinical mode requires authentication.</p>
        </div>
        <input
          className="input-field w-full"
          placeholder="Username"
          autoComplete="username"
          value={form.username}
          onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
        />
        <input
          className="input-field w-full"
          type="password"
          placeholder="Password"
          autoComplete="current-password"
          value={form.password}
          onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
        />
        <button type="submit" className="btn-primary w-full">Sign in</button>
      </form>
    </div>
  );
};

export default LoginModal;
