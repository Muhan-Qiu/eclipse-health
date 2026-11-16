import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AppProviders } from "@/app/providers";
import { SplashScreen } from "@/branding/SplashScreen";
import "./index.css";
import "./styles/v45-layout.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <SplashScreen>
      <AppProviders>
        <App />
      </AppProviders>
    </SplashScreen>
  </React.StrictMode>,
);
