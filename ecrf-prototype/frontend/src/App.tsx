import { Navigate, Outlet, Route, Routes, useLocation, useParams } from "react-router-dom";
import AuthProvider from "./auth/AuthProvider";
import { useAuth } from "./auth/useAuth";
import type { OrgType } from "./api/types";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import DataEntry from "./pages/DataEntry";
import DataReview from "./pages/DataReview";
import EcrfStatus from "./pages/EcrfStatus";
import Login from "./pages/Login";
import Patients from "./pages/Patients";
import Protocols from "./pages/Protocols";
import ProtocolUpload from "./pages/ProtocolUpload";
import Queries from "./pages/Queries";
import Review from "./pages/Review";
import Sites from "./pages/Sites";
import Studies from "./pages/Studies";
import SponsorStudies from "./pages/SponsorStudies";
import Visits from "./pages/Visits";
import WorkspaceDashboard from "./pages/WorkspaceDashboard";

const HOME: Record<OrgType, string> = { sponsor: "/sponsor", site: "/site" };

/* Everything below /login needs a session. While /me is still loading we
   render nothing rather than flash the login page at a signed-in user. */
function RequireAuth() {
  const { me, loading } = useAuth();
  const { pathname, search } = useLocation();
  if (loading) return null;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(pathname + search)}`} replace />;
  return <Outlet />;
}

/* Each portal belongs to one organisation type. Opening the other one
   sends you to your own home instead of showing an empty page. */
function Portal({ type }: { type: OrgType }) {
  const { me } = useAuth();
  if (me && me.org.type !== type) return <Navigate to={HOME[me.org.type]} replace />;
  return <Layout><Outlet /></Layout>;
}

function Home() {
  const { me } = useAuth();
  return <Navigate to={me ? HOME[me.org.type] : "/login"} replace />;
}

/* Old bookmarks from before the portals existed. */
function Legacy({ to }: { to: (id: string) => string }) {
  const { id = "" } = useParams();
  return <Navigate to={to(id)} replace />;
}

function StudyProtocols() {
  const { studyId } = useParams();
  return <Protocols key={studyId} studyId={Number(studyId)} />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<Home />} />

          <Route element={<Portal type="sponsor" />}>
            <Route path="/sponsor" element={<WorkspaceDashboard />} />
            <Route path="/sponsor/studies" element={<SponsorStudies />} />
            <Route path="/sponsor/studies/:studyId" element={<StudyProtocols />} />
            <Route path="/sponsor/protocols" element={<Protocols />} />
            <Route path="/sponsor/upload" element={<ProtocolUpload />} />
            <Route path="/sponsor/ecrfs" element={<Protocols destination="review" />} />
            <Route path="/sponsor/ecrf-status" element={<EcrfStatus />} />
            <Route path="/sponsor/data" element={<Protocols destination="data" />} />
            <Route path="/sponsor/reports" element={<Protocols destination="dashboard" />} />
            <Route path="/sponsor/queries" element={<Queries />} />
            <Route path="/sponsor/p/:id/visits" element={<Visits />} />
            <Route path="/sponsor/p/:id/review" element={<Review />} />
            <Route path="/sponsor/p/:id/sites" element={<Sites />} />
            <Route path="/sponsor/p/:id/data" element={<DataReview />} />
            <Route path="/sponsor/p/:id/dashboard" element={<Dashboard />} />
          </Route>

          <Route element={<Portal type="site" />}>
            <Route path="/site" element={<Studies />} />
            <Route path="/site/queries" element={<Queries />} />
            <Route path="/site/s/:id/patients" element={<Patients />} />
            <Route path="/site/s/:id/patients/:subject" element={<DataEntry />} />
          </Route>

          <Route path="/review/:id" element={<Legacy to={(id) => `/sponsor/p/${id}/review`} />} />
          <Route path="/dashboard/:id" element={<Legacy to={(id) => `/sponsor/p/${id}/dashboard`} />} />
          <Route path="/data/:id" element={<Legacy to={(id) => `/site/s/${id}/patients`} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
