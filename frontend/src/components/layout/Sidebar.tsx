import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import {
  LayoutDashboard,
  MessageSquare,
  Database,
  Search,
  History,
  Users,
  ShieldCheck,
  Activity,
  BarChart3,
  Settings as SettingsIcon,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Bot,
  User as UserIcon,
} from 'lucide-react';
import { Badge } from '../ui/Badge';

interface SidebarProps {
  isMobileOpen: boolean;
  setIsMobileOpen: (open: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isMobileOpen, setIsMobileOpen }) => {
  const [collapsed, setCollapsed] = useState<boolean>(false);
  const { user, role, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItemClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 group relative ${
      isActive
        ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-semibold'
        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
    }`;

  const roleVariant = role === 'ADMIN' ? 'cyan' : role === 'USER' ? 'green' : 'slate';

  return (
    <>
      {/* Mobile backdrop */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-950/80 backdrop-blur-sm md:hidden"
          onClick={() => setIsMobileOpen(false)}
        />
      )}

      <aside
        className={`fixed top-0 bottom-0 left-0 z-40 flex flex-col bg-slate-900 border-r border-slate-800/80 transition-all duration-300 ${
          collapsed ? 'w-20' : 'w-64'
        } ${
          isMobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        {/* Header / Logo */}
        <div className="flex items-center justify-between h-16 px-4 border-b border-slate-800">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 text-white shadow-lg shadow-cyan-500/20 shrink-0">
              <Bot className="w-6 h-6" />
            </div>
            {!collapsed && (
              <div className="flex flex-col overflow-hidden">
                <span className="font-bold text-slate-100 text-base leading-tight tracking-tight">AI-QA</span>
                <span className="text-[10px] text-slate-400 font-medium truncate">AI Question-Answering</span>
              </div>
            )}
          </div>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="hidden md:flex items-center justify-center w-7 h-7 text-slate-400 hover:text-slate-100 bg-slate-800/80 hover:bg-slate-800 border border-slate-700/60 rounded-lg transition-colors"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation Items */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
          {/* Main Group */}
          <div>
            {!collapsed && (
              <p className="px-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
                Main
              </p>
            )}
            <nav className="space-y-1">
              <NavLink to="/dashboard" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
                <LayoutDashboard className="w-5 h-5 shrink-0" />
                {!collapsed && <span>Dashboard</span>}
              </NavLink>
              <NavLink to="/chat" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
                <MessageSquare className="w-5 h-5 shrink-0" />
                {!collapsed && <span>Chat</span>}
              </NavLink>
              <NavLink to="/knowledge-base" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
                <Database className="w-5 h-5 shrink-0" />
                {!collapsed && <span>Knowledge Base</span>}
              </NavLink>
              <NavLink to="/search" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
                <Search className="w-5 h-5 shrink-0" />
                {!collapsed && <span>Search</span>}
              </NavLink>
              <NavLink to="/history" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
                <History className="w-5 h-5 shrink-0" />
                {!collapsed && <span>Chat History</span>}
              </NavLink>
            </nav>
          </div>

          {/* Admin Section (ADMIN role only) */}
          {role === 'ADMIN' && (
            <div>
              {!collapsed && (
                <p className="px-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  Admin
                </p>
              )}
              <nav className="space-y-1">
                <NavLink to="/users" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
                  <Users className="w-5 h-5 shrink-0" />
                  {!collapsed && <span>Users</span>}
                </NavLink>
                <NavLink to="/audit" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
                  <ShieldCheck className="w-5 h-5 shrink-0" />
                  {!collapsed && <span>Audit Logs</span>}
                </NavLink>
              </nav>
            </div>
          )}

          {/* System Section */}
          <div>
            {!collapsed && (
              <p className="px-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
                System
              </p>
            )}
            <nav className="space-y-1">
              <NavLink to="/health" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
                <Activity className="w-5 h-5 shrink-0" />
                {!collapsed && <span>System Health</span>}
              </NavLink>
              {role === 'ADMIN' && (
                <NavLink to="/metrics" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
                  <BarChart3 className="w-5 h-5 shrink-0" />
                  {!collapsed && <span>Metrics</span>}
                </NavLink>
              )}
            </nav>
          </div>
        </div>

        {/* Bottom Section */}
        <div className="p-3 border-t border-slate-800 bg-slate-900/90 space-y-2">
          <NavLink to="/settings" className={navItemClass} onClick={() => setIsMobileOpen(false)}>
            <SettingsIcon className="w-5 h-5 shrink-0" />
            {!collapsed && <span>Settings</span>}
          </NavLink>

          {/* User profile summary */}
          <div className="pt-2">
            <div className={`flex items-center gap-3 p-2 rounded-xl bg-slate-800/40 border border-slate-800 ${collapsed ? 'justify-center' : ''}`}>
              <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-slate-700 text-slate-200 font-bold shrink-0 text-xs">
                {user?.username ? user.username.substring(0, 2).toUpperCase() : <UserIcon className="w-4 h-4" />}
              </div>
              {!collapsed && (
                <div className="flex flex-col min-w-0 flex-1">
                  <span className="text-xs font-semibold text-slate-200 truncate">{user?.username || 'User'}</span>
                  <div className="mt-0.5">
                    <Badge variant={roleVariant} size="sm">{role}</Badge>
                  </div>
                </div>
              )}
            </div>
          </div>

          <button
            onClick={handleLogout}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 transition-colors ${
              collapsed ? 'justify-center' : ''
            }`}
            title="Log out"
          >
            <LogOut className="w-4 h-4 shrink-0" />
            {!collapsed && <span>Log out</span>}
          </button>
        </div>
      </aside>
    </>
  );
};
