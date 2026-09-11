import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { ThemeProvider } from './hooks/useTheme';
import { Overview } from './pages/Overview';
import { NewAssessment } from './pages/NewAssessment';
import { Assessments } from './pages/Assessments';
import { AssessmentResult } from './pages/AssessmentResult';
import { Findings } from './pages/Findings';
import { Evidence } from './pages/Evidence';
import { AuditTrail } from './pages/AuditTrail';
import { Capabilities } from './pages/Capabilities';

export function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Overview />} />
            <Route path="new" element={<NewAssessment />} />
            <Route path="assessments" element={<Assessments />} />
            <Route path="assessments/:id/result" element={<AssessmentResult />} />
            <Route path="assessments/:id/findings" element={<Findings />} />
            <Route path="assessments/:id/evidence" element={<Evidence />} />
            <Route path="assessments/:id/audit" element={<AuditTrail />} />
            <Route path="audit" element={<AuditTrail />} />
            <Route path="findings" element={<Findings />} />
            <Route path="capabilities" element={<Capabilities />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
