import { useCallback, useEffect, useMemo, useReducer, type FormEvent, type SetStateAction } from "react";
import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { useAuth } from "../../contexts/AuthContext";
import {
  getApiErrorMessage,
  organizationsApi,
  type Organization,
  type OrganizationMember,
  type OrganizationRoleCapabilities,
} from "../../lib/api";
import { showError, showSuccess } from "../../lib/toast";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ConfirmButton,
  FormField,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
} from "@/components/ui";

const ROLE_OPTIONS: { value: OrganizationMember["role"]; label: string }[] = [
  { value: "owner", label: "Owner" },
  { value: "admin", label: "Admin" },
  { value: "member", label: "Member" },
  { value: "viewer", label: "Viewer" },
];

const formatDateTime = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const ROLE_MATRIX: Array<{
  role: OrganizationMember["role"];
  label: string;
  description: string;
}> = [
  { role: "owner", label: "Owner", description: "Full tenant governance, including retention and exports." },
  { role: "admin", label: "Admin", description: "Operational control without ownership transfer." },
  { role: "member", label: "Member", description: "Can work with curated memory, but not govern the tenant." },
  { role: "viewer", label: "Viewer", description: "Read-only access to memory and runtime context." },
];

const capabilityLabel: Record<keyof OrganizationRoleCapabilities, string> = {
  can_view_observations: "View observations",
  can_delete_observations: "Delete observations",
  can_manage_retention: "Manage retention",
  can_export_memory_data: "Export memory data",
  can_manage_members: "Manage members",
};

type OrganizationGovernanceState = {
  current_role_capabilities: OrganizationRoleCapabilities;
  role_capabilities: Record<OrganizationMember["role"], OrganizationRoleCapabilities>;
};

type OrganizationFormState = { email: string; role: OrganizationMember["role"] };

type OrganizationPageState = {
  organization: Organization | null;
  role: OrganizationMember["role"] | null;
  governance: OrganizationGovernanceState | null;
  members: OrganizationMember[];
  loading: boolean;
  membersLoading: boolean;
  error: string | null;
  memberError: string | null;
  isSubmitting: boolean;
  updatingMemberId: string | null;
  formState: OrganizationFormState;
};

type OrganizationPageAction = {
  patch: Partial<OrganizationPageState> | ((state: OrganizationPageState) => Partial<OrganizationPageState>);
};

const initialOrganizationPageState: OrganizationPageState = {
  organization: null,
  role: null,
  governance: null,
  members: [],
  loading: true,
  membersLoading: false,
  error: null,
  memberError: null,
  isSubmitting: false,
  updatingMemberId: null,
  formState: { email: "", role: "member" },
};

function organizationPageReducer(
  state: OrganizationPageState,
  action: OrganizationPageAction,
): OrganizationPageState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

function OrganizationOverviewGrid({
  organization,
  role,
  userRole,
  governance,
}: {
  organization: Organization;
  role: OrganizationMember["role"] | null;
  userRole?: OrganizationMember["role"] | null;
  governance: OrganizationGovernanceState | null;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
      <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="text-base">Workspace details</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3 xl:grid-cols-1">
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase">Name</p>
            <p className="mt-1 text-sm font-semibold">{organization.name}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase">Workspace ID</p>
            <p className="mt-1 text-xs font-mono text-muted-foreground">{organization.id}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase">Your role</p>
            <div className="mt-2 flex items-center gap-2">
              <Badge variant="outline" className="capitalize">
                {role ?? userRole ?? "member"}
              </Badge>
              {governance ? (
                <span className="text-xs text-muted-foreground">
                  {governance.current_role_capabilities.can_manage_retention
                    ? "Can govern memory retention and exports."
                    : "Can inspect memory, but governance stays with admins."}
                </span>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="text-base">Memory governance by role</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {ROLE_MATRIX.map((roleEntry) => {
            const capabilities = governance?.role_capabilities[roleEntry.role];
            const enabledCapabilities = capabilities
              ? (Object.entries(capabilities) as Array<[keyof OrganizationRoleCapabilities, boolean]>).flatMap(
                  ([key, enabled]) => (enabled ? [capabilityLabel[key]] : []),
                )
              : [];

            return (
              <div key={roleEntry.role} className="rounded-xl border border-border/50 bg-background/70 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-medium text-foreground">{roleEntry.label}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{roleEntry.description}</p>
                  </div>
                  <Badge variant={roleEntry.role === role ? "secondary" : "outline"} className="capitalize">
                    {roleEntry.role === role ? "Current role" : roleEntry.label}
                  </Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {enabledCapabilities.map((label) => (
                    <Badge key={label} variant="outline">
                      {label}
                    </Badge>
                  ))}
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

function MemoryGovernanceAlert() {
  return (
    <Alert className="border-sky-500/30 bg-sky-500/10 text-sky-800 dark:text-sky-100">
      <ShieldCheck className="size-4" />
      <AlertDescription className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <span>Knowledge retention changes and exported reporting are restricted to owner and admin roles.</span>
        <Link href="/admin/operations" className="inline-flex items-center gap-1 text-sm font-medium">
          Review policies and retention
          <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </AlertDescription>
    </Alert>
  );
}

function OrganizationPageHeader() {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-2xl sm:text-3xl font-semibold">Workspace Access</h1>
      <p className="text-sm text-muted-foreground">Manage your company workspace profile and member access.</p>
    </div>
  );
}

export default function OrganizationPage() {
  const { user } = useAuth();
  const [pageState, dispatchPageState] = useReducer(organizationPageReducer, initialOrganizationPageState);
  const {
    organization,
    role,
    governance,
    members,
    loading,
    membersLoading,
    error,
    memberError,
    isSubmitting,
    updatingMemberId,
    formState,
  } = pageState;
  const setPageField = useCallback(
    <K extends keyof OrganizationPageState>(key: K, value: SetStateAction<OrganizationPageState[K]>) => {
      dispatchPageState({
        patch: (current) => ({ [key]: resolveStateAction(value, current[key]) }) as Partial<OrganizationPageState>,
      });
    },
    [],
  );
  const setOrganization = useCallback((value: SetStateAction<Organization | null>) => setPageField("organization", value), [setPageField]);
  const setRole = useCallback((value: SetStateAction<OrganizationMember["role"] | null>) => setPageField("role", value), [setPageField]);
  const setGovernance = useCallback((value: SetStateAction<OrganizationGovernanceState | null>) => setPageField("governance", value), [setPageField]);
  const setMembers = useCallback((value: SetStateAction<OrganizationMember[]>) => setPageField("members", value), [setPageField]);
  const setLoading = useCallback((value: SetStateAction<boolean>) => setPageField("loading", value), [setPageField]);
  const setMembersLoading = useCallback((value: SetStateAction<boolean>) => setPageField("membersLoading", value), [setPageField]);
  const setError = useCallback((value: SetStateAction<string | null>) => setPageField("error", value), [setPageField]);
  const setMemberError = useCallback((value: SetStateAction<string | null>) => setPageField("memberError", value), [setPageField]);
  const setIsSubmitting = useCallback((value: SetStateAction<boolean>) => setPageField("isSubmitting", value), [setPageField]);
  const setUpdatingMemberId = useCallback((value: SetStateAction<string | null>) => setPageField("updatingMemberId", value), [setPageField]);
  const setFormState = useCallback((value: SetStateAction<OrganizationFormState>) => setPageField("formState", value), [setPageField]);

  const canManageMembers = useMemo(
    () =>
      role === "owner" ||
      role === "admin" ||
      user?.organization_role === "owner" ||
      user?.organization_role === "admin",
    [role, user?.organization_role],
  );

  const loadOrganization = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await organizationsApi.me();
      setOrganization(response.organization);
      setRole(response.role);
      setGovernance(response.governance);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load workspace access details."));
    } finally {
      setLoading(false);
    }
  }, [setError, setGovernance, setLoading, setOrganization, setRole]);

  const loadMembers = useCallback(async () => {
    if (!canManageMembers) return;
    setMembersLoading(true);
    setMemberError(null);
    try {
      const response = await organizationsApi.listMembers();
      setMembers(response);
    } catch (err: unknown) {
      setMemberError(getApiErrorMessage(err, "Failed to load members."));
    } finally {
      setMembersLoading(false);
    }
  }, [canManageMembers, setMemberError, setMembers, setMembersLoading]);

  useEffect(() => {
    void loadOrganization();
  }, [loadOrganization]);

  useEffect(() => {
    if (organization && canManageMembers) {
      void loadMembers();
    }
  }, [organization, canManageMembers, loadMembers]);

  const handleAddMember = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canManageMembers || isSubmitting) return;

    setIsSubmitting(true);
    setMemberError(null);
    try {
      const created = await organizationsApi.addMember({
        email: formState.email.trim(),
        role: formState.role,
      });
      setMembers((prev) => [created, ...prev]);
      setFormState({ email: "", role: "member" });
      showSuccess("Member added.");
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, "Failed to add member.");
      setMemberError(message);
      showError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRoleChange = async (member: OrganizationMember, newRole: OrganizationMember["role"]) => {
    if (!canManageMembers) return;
    setUpdatingMemberId(member.user_id);
    try {
      const updated = await organizationsApi.updateMember(member.user_id, { role: newRole });
      setMembers((prev) => prev.map((item) => (item.user_id === updated.user_id ? updated : item)));
      showSuccess("Member role updated.");
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, "Failed to update member role.");
      setMemberError(message);
      showError(message);
    } finally {
      setUpdatingMemberId(null);
    }
  };

  const handleRemove = async (member: OrganizationMember) => {
    if (!canManageMembers) return;
    setUpdatingMemberId(member.user_id);
    try {
      await organizationsApi.removeMember(member.user_id);
      setMembers((prev) => prev.filter((item) => item.user_id !== member.user_id));
      showSuccess("Member removed.");
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, "Failed to remove member.");
      setMemberError(message);
      showError(message);
    } finally {
      setUpdatingMemberId(null);
    }
  };

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <OrganizationPageHeader />

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Spinner className="size-5" />
              Loading workspace access…
            </div>
          ) : organization ? (
            <OrganizationOverviewGrid
              organization={organization}
              role={role}
              userRole={user?.organization_role}
              governance={governance}
            />
          ) : null}

          {governance ? <MemoryGovernanceAlert /> : null}

          <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Members</CardTitle>
              <Button variant="outline" size="sm" onClick={() => void loadMembers()} disabled={!canManageMembers}>
                Refresh
              </Button>
            </CardHeader>
            <CardContent className="space-y-6">
              {!canManageMembers && (
                <Alert>
                  <AlertDescription>You have read-only access. Ask an admin to manage members.</AlertDescription>
                </Alert>
              )}

              {canManageMembers && (
                <form onSubmit={handleAddMember} className="grid gap-4 md:grid-cols-[1.4fr_1fr_auto]">
                  <FormField label="Member email" htmlFor="member-email">
                    <Input
                      id="member-email"
                      type="email"
                      value={formState.email}
                      onChange={(event) => setFormState((prev) => ({ ...prev, email: event.target.value }))}
                      placeholder="teammate@company.com"
                      required
                    />
                  </FormField>
                  <FormField label="Role" htmlFor="member-role">
                    <Select
                      value={formState.role}
                      onValueChange={(value) =>
                        setFormState((prev) => ({
                          ...prev,
                          role: value as OrganizationMember["role"],
                        }))
                      }
                    >
                      <SelectTrigger id="member-role">
                        <SelectValue placeholder="Select role" />
                      </SelectTrigger>
                      <SelectContent>
                        {ROLE_OPTIONS.map((roleOption) => (
                          <SelectItem key={roleOption.value} value={roleOption.value}>
                            {roleOption.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormField>
                  <div className="flex items-end">
                    <Button type="submit" disabled={isSubmitting || !formState.email.trim()}>
                      {isSubmitting ? (
                        <>
                          <Spinner size="xs" className="mr-2" />
                          Adding…
                        </>
                      ) : (
                        "Add member"
                      )}
                    </Button>
                  </div>
                </form>
              )}

              {memberError && (
                <Alert variant="destructive">
                  <AlertDescription>{memberError}</AlertDescription>
                </Alert>
              )}

              {canManageMembers ? (
                membersLoading ? (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Spinner className="size-5" />
                    Loading members…
                  </div>
                ) : members.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No members found.</p>
                ) : (
                  <div className="space-y-3">
                    {members.map((member) => (
                      <div
                        key={member.user_id}
                        className="flex flex-col gap-3 rounded-lg border border-border/60 bg-background/60 p-4 md:flex-row md:items-center md:justify-between"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium">{member.email}</p>
                            {member.is_default && <Badge variant="outline">Default</Badge>}
                          </div>
                          <p className="text-xs text-muted-foreground">Joined {formatDateTime(member.joined_at)}</p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Select
                            value={member.role}
                            onValueChange={(value) => handleRoleChange(member, value as OrganizationMember["role"])}
                            disabled={updatingMemberId === member.user_id}
                          >
                            <SelectTrigger className="w-[140px]">
                              <SelectValue placeholder="Role" />
                            </SelectTrigger>
                            <SelectContent>
                              {ROLE_OPTIONS.map((roleOption) => (
                                <SelectItem key={roleOption.value} value={roleOption.value}>
                                  {roleOption.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <ConfirmButton
                            variant="destructive"
                            size="sm"
                            title={`Remove ${member.email}?`}
                            description="This member will lose access to the workspace."
                            onConfirm={() => handleRemove(member)}
                            disabled={updatingMemberId === member.user_id}
                          >
                            Remove
                          </ConfirmButton>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              ) : null}
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
