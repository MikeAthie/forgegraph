import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { useAuth } from "../../contexts/AuthContext";
import {
  getApiErrorMessage,
  organizationsApi,
  type Organization,
  type OrganizationMember,
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

export default function OrganizationPage() {
  const { user } = useAuth();
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [role, setRole] = useState<OrganizationMember["role"] | null>(null);
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [membersLoading, setMembersLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [memberError, setMemberError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [updatingMemberId, setUpdatingMemberId] = useState<string | null>(null);

  const [formState, setFormState] = useState<{ email: string; role: OrganizationMember["role"] }>({
    email: "",
    role: "member",
  });

  const canManageMembers = useMemo(
    () => role === "owner" || role === "admin" || user?.organization_role === "owner" || user?.organization_role === "admin",
    [role, user?.organization_role],
  );

  const loadOrganization = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await organizationsApi.me();
      setOrganization(response.organization);
      setRole(response.role);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load organization details."));
    } finally {
      setLoading(false);
    }
  }, []);

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
  }, [canManageMembers]);

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
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl sm:text-3xl font-semibold">Organization</h1>
            <p className="text-sm text-muted-foreground">
              Manage your organization profile and member access.
            </p>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Spinner className="h-5 w-5" />
              Loading organization...
            </div>
          ) : organization ? (
            <Card className="border-border/60 bg-card/60 backdrop-blur-sm">
              <CardHeader>
                <CardTitle className="text-base">Organization details</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-3">
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase">Name</p>
                  <p className="mt-1 text-sm font-semibold">{organization.name}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase">Organization ID</p>
                  <p className="mt-1 text-xs font-mono text-muted-foreground">{organization.id}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase">Your role</p>
                  <p className="mt-1 text-sm capitalize">{role ?? user?.organization_role ?? "member"}</p>
                </div>
              </CardContent>
            </Card>
          ) : null}

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
                  <AlertDescription>
                    You have read-only access. Ask an admin to manage members.
                  </AlertDescription>
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
                          Adding...
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
                    <Spinner className="h-5 w-5" />
                    Loading members...
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
                          <p className="text-xs text-muted-foreground">
                            Joined {formatDateTime(member.joined_at)}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Select
                            value={member.role}
                            onValueChange={(value) =>
                              handleRoleChange(member, value as OrganizationMember["role"])
                            }
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
                            description="This member will lose access to the organization."
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
