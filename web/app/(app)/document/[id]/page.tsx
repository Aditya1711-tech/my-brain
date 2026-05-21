import { DocumentDetailPage } from "@/components/document/document-detail-page";

export default async function DocumentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <DocumentDetailPage documentId={id} />;
}
