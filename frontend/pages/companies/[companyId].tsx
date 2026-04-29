import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/router";

import { CompanyWorkspaceShell } from "@/components/company/CompanyWorkspaceShell";
import { companyRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type { CompanyWorkspaceVM } from "@/domain/translation";

export default function CompanyWorkspacePage() {
  const router = useRouter();
  const companyIdParam = router.query.companyId;
  const companyId = Array.isArray(companyIdParam) ? companyIdParam[0] : companyIdParam;
  const questParam = router.query.quest;
  const questMode = Array.isArray(questParam) ? questParam[0] === "1" : questParam === "1";

  const [workspace, setWorkspace] = useState<CompanyWorkspaceVM>({
    company: null,
    operations: [],
    pendingApprovalCount: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCompanyWorkspace = useCallback(async () => {
    if (!companyId) {
      setError("Missing company id.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      setWorkspace(await companyRepository.getWorkspace(companyId));
    } catch (loadError: unknown) {
      setError(translateProductError(loadError, "company"));
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    void loadCompanyWorkspace();
  }, [loadCompanyWorkspace, router.isReady]);

  return (
    <CompanyWorkspaceShell
      companyId={companyId ?? ""}
      company={workspace.company}
      operations={workspace.operations}
      pendingApprovalCount={workspace.pendingApprovalCount}
      loading={loading}
      error={error}
      onRefresh={loadCompanyWorkspace}
      questMode={questMode}
    />
  );
}
