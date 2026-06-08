import type { GetServerSideProps } from "next";

export const getServerSideProps: GetServerSideProps = async ({ query }) => ({
  redirect: {
    destination: typeof query.item === "string" ? `/approvals?item=${encodeURIComponent(query.item)}` : "/approvals",
    permanent: false,
  },
});

export default function InboxRedirectPage() {
  return null;
}
