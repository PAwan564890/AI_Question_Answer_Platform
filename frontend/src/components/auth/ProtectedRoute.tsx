import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Role } from '../../types/api';
import { ShieldAlert, Loader2 } from 'lucide-react';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: Role[];
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, allowedRoles }) => {
  const { isAuthenticated, user, role, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4">
        <Loader2 className="w-10 h-10 text-cyan-500 animate-spin mb-4" />
        <p className="text-slate-400 text-sm font-medium">Authenticating user session...</p>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && role && !allowedRoles.includes(role)) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-6 text-center">
        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-2xl mb-6">
          <ShieldAlert className="w-12 h-12 text-red-400 mx-auto" />
        </div>
        <h1 className="text-2xl font-bold text-slate-100 mb-2">Access Denied</h1>
        <p className="text-slate-400 max-w-md mb-6">
          Your current role (<span className="text-cyan-400 font-mono font-semibold">{role}</span>) does not have permission to access this page. Please contact your system administrator for access.
        </p>
        <a
          href="/dashboard"
          className="px-5 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-xl transition-colors border border-slate-700"
        >
          Return to Dashboard
        </a>
      </div>
    );
  }

  return <>{children}</>;
};
