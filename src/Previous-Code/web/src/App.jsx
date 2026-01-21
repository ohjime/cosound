import { createBrowserRouter, RouterProvider, Outlet } from "react-router-dom";
import { Login } from "./Pages/Login";
import { AuthCallback } from "./Pages/AuthCallback";
import { AuthTest } from "./Pages/AuthTest";
import Home from "./Pages/Home";
import Vote from "./Pages/Vote";
import VoteConfirmation from "./Pages/VoteConfirmation";
import Preferences from "./Pages/Preferences";
import PreferencesSurvey from "./Pages/PreferencesSurvey";
import { Settings } from "./Pages/Settings";
import { ProtectedRoute } from "./Components/ProtectedRoute";
import { useSessionValidator } from "./hooks/useSessionValidator";

// Layout with permanent Sidebar for authenticated routes
const Layout = () => {
  // Validate session on mount and listen for auth changes
  useSessionValidator();

  return (
    <div >
          <Outlet />
    </div>
  );
};

const router = createBrowserRouter([
  // Public routes
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/auth/callback",
    element: <AuthCallback />,
  },
  {
    path: "/auth/test",
    element: <AuthTest />,
  },
  {
    path: "/preferences",
    element: <Preferences />,
  },
  {
    path: "/preferences/:step",
    element: <PreferencesSurvey />,
  },
  // Public voting routes (no authentication required)
  {
    path: "/",
    element: <Layout />,
    children: [
      {
        index: true,
        element: <Home />,
      },
      {
        path: "vote",
        element: <Vote />,
      },
      {
        path: "vote/:voteValue",
        element: <VoteConfirmation />,
      },
      // Protected routes nested here but with protection
      {
        path: "settings",
        element: (
          <ProtectedRoute>
            <Settings />
          </ProtectedRoute>
        ),
      },
    ],
  },
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
