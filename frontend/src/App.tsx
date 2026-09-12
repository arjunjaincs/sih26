import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { AssessmentWorkspaceLayout } from './layouts/AssessmentWorkspaceLayout';
import { ThemeProvider } from './hooks/useTheme';
import { Overview } from './pages/Overview';
import { NewAssessment } from './pages/NewAssessment';
import { Assessments } from './pages/Assessments';
import { AssessmentResult } from './pages/AssessmentResult';
import { Findings } from './pages/Findings';
import { Evidence } from './pages/Evidence';
import { Provenance } from './pages/Provenance';
import { AuditTrail } from './pages/AuditTrail';
import { ScopeLimitations } from './pages/ScopeLimitations';
import { Capabilities } from './pages/Capabilities';
import { Settings } from './pages/Settings';

export function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Overview />} />
            <Route path="new" element={<NewAssessment />} />
            <Route path="assessments" element={<Assessments />} />
            <Route path="assessments/new" element={<NewAssessment />} />

            {/* Unified Forensic Assessment Workspace */}
            <Route path="assessments/:id" element={<AssessmentWorkspaceLayout />}>
              <Route index element={<Navigate to="result" replace />} />
              <Route path="result" element={<AssessmentResult />} />
              <Route path="findings" element={<Findings />} />
              <Route path="evidence" element={<Evidence />} />
              <Route path="provenance" element={<Provenance />} />
              <Route path="audit" element={<AuditTrail />} />
              <Route path="limitations" element={<ScopeLimitations />} />
            </Route>

            {/* Standalone / Auxiliary routes */}
            <Route path="audit" element={<AuditTrail />} />
            <Route path="findings" element={<Findings />} />
            <Route path="capabilities" element={<Capabilities />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
