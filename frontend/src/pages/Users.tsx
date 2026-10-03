import React, { useState, useEffect } from 'react';
import { adminApi } from '../api/admin';
import { Role, UserCreate, UserOut, UserUpdate } from '../types/api';
import { CustomApiError } from '../api/client';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { SkeletonTable } from '../components/ui/Skeleton';
import {
  Users as UsersIcon,
  UserPlus,
  RefreshCw,
  Edit2,
  Shield,
  CheckCircle2,
  XCircle,
  Calendar,
  AlertCircle,
} from 'lucide-react';
import { toast } from 'sonner';

export const Users: React.FC = () => {
  const [users, setUsers] = useState<UserOut[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Create User Modal
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [newUsername, setNewUsername] = useState<string>('');
  const [newPassword, setNewPassword] = useState<string>('');
  const [newRole, setNewRole] = useState<Role>('USER');
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Edit User Modal
  const [editUser, setEditUser] = useState<UserOut | null>(null);
  const [editRole, setEditRole] = useState<Role>('USER');
  const [editIsActive, setEditIsActive] = useState<boolean>(true);
  const [editPassword, setEditPassword] = useState<string>('');
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await adminApi.listUsers({ limit: 100 });
      setUsers(data);
    } catch {
      toast.error('Failed to load system users.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword.trim()) {
      setCreateError('Username and password are required.');
      return;
    }

    setCreateError(null);
    setCreateSubmitting(true);

    try {
      await adminApi.createUser({
        username: newUsername.trim(),
        password: newPassword,
        role: newRole,
      });

      toast.success(`User ${newUsername} created successfully!`);
      setIsCreateOpen(false);
      setNewUsername('');
      setNewPassword('');
      setNewRole('USER');
      fetchUsers();
    } catch (err) {
      if (err instanceof CustomApiError) {
        setCreateError(err.message);
      } else {
        setCreateError('Failed to create user.');
      }
    } finally {
      setCreateSubmitting(false);
    }
  };

  const openEditModal = (u: UserOut) => {
    setEditUser(u);
    setEditRole(u.role);
    setEditIsActive(u.is_active);
    setEditPassword('');
    setEditError(null);
  };

  const handleUpdateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editUser) return;

    setEditError(null);
    setEditSubmitting(true);

    const payload: UserUpdate = {
      role: editRole,
      is_active: editIsActive,
    };
    if (editPassword.trim()) {
      payload.password = editPassword.trim();
    }

    try {
      await adminApi.updateUser(editUser.id, payload);
      toast.success(`User ${editUser.username} updated!`);
      setEditUser(null);
      fetchUsers();
    } catch (err) {
      if (err instanceof CustomApiError) {
        setEditError(err.message);
      } else {
        setEditError('Failed to update user.');
      }
    } finally {
      setEditSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 bg-slate-900/60 border border-slate-800/80 rounded-2xl">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <UsersIcon className="w-5 h-5 text-cyan-400" />
            <span>User Management</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Manage application user accounts, roles, active statuses, and access permissions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchUsers}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />}
          >
            Refresh
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => setIsCreateOpen(true)}
            icon={<UserPlus className="w-4 h-4" />}
          >
            Create User
          </Button>
        </div>
      </div>

      {/* Users Table */}
      {loading ? (
        <SkeletonTable rows={4} />
      ) : (
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-900/90 text-slate-400 font-semibold border-b border-slate-800 uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3.5">Username</th>
                  <th className="px-5 py-3.5">Role</th>
                  <th className="px-5 py-3.5">Status</th>
                  <th className="px-5 py-3.5">Created At</th>
                  <th className="px-5 py-3.5">Last Login</th>
                  <th className="px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {users.map((u) => {
                  const roleVariant = u.role === 'ADMIN' ? 'cyan' : u.role === 'USER' ? 'green' : 'slate';
                  return (
                    <tr key={u.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-5 py-4 font-bold text-slate-200">
                        <span>{u.username}</span>
                      </td>
                      <td className="px-5 py-4">
                        <Badge variant={roleVariant} size="sm" icon={<Shield className="w-3 h-3" />}>
                          {u.role}
                        </Badge>
                      </td>
                      <td className="px-5 py-4 font-medium">
                        {u.is_active ? (
                          <div className="flex items-center gap-1.5 text-emerald-400">
                            <CheckCircle2 className="w-4 h-4" />
                            <span>Active</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 text-rose-400">
                            <XCircle className="w-4 h-4" />
                            <span>Disabled</span>
                          </div>
                        )}
                      </td>
                      <td className="px-5 py-4 text-slate-400 font-mono">
                        <div className="flex items-center gap-1.5">
                          <Calendar className="w-3.5 h-3.5 text-slate-500" />
                          <span>{new Date(u.created_at).toLocaleDateString()}</span>
                        </div>
                      </td>
                      <td className="px-5 py-4 text-slate-400 font-mono">
                        {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}
                      </td>
                      <td className="px-5 py-4 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditModal(u)}
                          icon={<Edit2 className="w-3.5 h-3.5" />}
                        >
                          Edit
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create User Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Create New User Account"
        subtitle="Password must be at least 10 characters and contain letters and numbers."
      >
        <form onSubmit={handleCreateUser} className="space-y-4">
          {createError && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <span>{createError}</span>
            </div>
          )}

          <Input
            label="Username"
            placeholder="e.g. analyst_john"
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
            required
          />

          <Input
            label="Password"
            type="password"
            placeholder="At least 10 chars with letters & numbers"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Assign Role
            </label>
            <select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as Role)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-cyan-500"
            >
              <option value="USER">USER — Full Chat & KB List/Search</option>
              <option value="ADMIN">ADMIN — Full System & User Management</option>
              <option value="READ_ONLY">READ_ONLY — Document Search Only</option>
            </select>
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
            <Button type="button" variant="ghost" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={createSubmitting}>
              Create Account
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit User Modal */}
      <Modal
        isOpen={!!editUser}
        onClose={() => setEditUser(null)}
        title={`Edit User: ${editUser?.username}`}
        subtitle="Update role, status, or reset account password."
      >
        <form onSubmit={handleUpdateUser} className="space-y-4">
          {editError && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <span>{editError}</span>
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
              Role
            </label>
            <select
              value={editRole}
              onChange={(e) => setEditRole(e.target.value as Role)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-slate-100 text-sm focus:outline-none focus:border-cyan-500"
            >
              <option value="USER">USER</option>
              <option value="ADMIN">ADMIN</option>
              <option value="READ_ONLY">READ_ONLY</option>
            </select>
          </div>

          <div className="flex items-center justify-between p-3 bg-slate-950 border border-slate-800 rounded-xl">
            <div>
              <span className="text-xs font-semibold text-slate-200 block">Account Status</span>
              <span className="text-[11px] text-slate-400">Toggle whether this user can authenticate</span>
            </div>
            <input
              type="checkbox"
              checked={editIsActive}
              onChange={(e) => setEditIsActive(e.target.checked)}
              className="w-5 h-5 accent-cyan-500 cursor-pointer"
            />
          </div>

          <Input
            label="Reset Password (Optional)"
            type="password"
            placeholder="Leave empty to keep current password"
            value={editPassword}
            onChange={(e) => setEditPassword(e.target.value)}
          />

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
            <Button type="button" variant="ghost" onClick={() => setEditUser(null)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" isLoading={editSubmitting}>
              Save Changes
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
