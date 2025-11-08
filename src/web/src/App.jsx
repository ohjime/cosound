import { createBrowserRouter, RouterProvider, Outlet } from "react-router-dom";
import { Login } from "./Pages/Login";
import { AuthCallback } from "./Pages/AuthCallback";
import Home from "./Pages/Home";
import { Settings } from "./Pages/Settings";
import { ProtectedRoute } from "./Components/ProtectedRoute";

// Layout with permanent Sidebar for authenticated routes
const Layout = () => {
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

  // Protected routes with Layout
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <Layout />
      </ProtectedRoute>
    ),
    children: [
      {
        index: true,
        element: <Home />,
      },
 

      {
        path: "settings",
        element: <Settings />,
      },
    ],
  },
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
