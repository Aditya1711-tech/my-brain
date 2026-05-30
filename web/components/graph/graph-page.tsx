"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import dynamic from "next/dynamic";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";

// Force graph must be client-side only (uses canvas)
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
});

interface EntityNode {
  id: string;
  canonical_name: string;
  entity_type: string;
  doc_count: number;
  // Added by react-force-graph at runtime
  x?: number;
  y?: number;
}

interface RelationshipLink {
  source: string;
  target: string;
  relation_type: string;
}

interface GraphData {
  nodes: EntityNode[];
  links: RelationshipLink[];
}

interface EntityDetail {
  id: string;
  canonical_name: string;
  entity_type: string;
  aliases: string[];
  documents: { id: string; original_filename: string; role: string }[];
  facts: { field_name: string; field_value: string }[];
}

const TYPE_COLORS: Record<string, string> = {
  person: "#3b82f6",
  organization: "#10b981",
  asset: "#f59e0b",
  location: "#8b5cf6",
  other: "#6b7280",
};

export function GraphPage() {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);
  const [selectedEntity, setSelectedEntity] = useState<EntityDetail | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };
    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  const loadGraph = useCallback(async () => {
    const supabase = createClient();

    // Load entities
    const { data: entities } = await supabase
      .from("entities")
      .select("id, canonical_name, entity_type");

    if (!entities || entities.length === 0) {
      setLoading(false);
      return;
    }

    // Load document_entities to compute doc_count per entity
    const { data: docEntities } = await supabase
      .from("document_entities")
      .select("entity_id");

    const docCounts: Record<string, number> = {};
    for (const de of docEntities ?? []) {
      docCounts[de.entity_id] = (docCounts[de.entity_id] ?? 0) + 1;
    }

    // Load relationships
    const { data: relationships } = await supabase
      .from("entity_relationships")
      .select("from_entity_id, to_entity_id, relation_type");

    const nodes: EntityNode[] = entities.map((e) => ({
      id: e.id,
      canonical_name: e.canonical_name,
      entity_type: e.entity_type,
      doc_count: docCounts[e.id] ?? 0,
    }));

    const entityIds = new Set(entities.map((e) => e.id));
    const links: RelationshipLink[] = (relationships ?? [])
      .filter((r) => entityIds.has(r.from_entity_id) && entityIds.has(r.to_entity_id))
      .map((r) => ({
        source: r.from_entity_id,
        target: r.to_entity_id,
        relation_type: r.relation_type,
      }));

    setGraphData({ nodes, links });
    setLoading(false);
  }, []);

  useEffect(() => {
    loadGraph(); // eslint-disable-line react-hooks/set-state-in-effect -- initial data fetch
  }, [loadGraph]);

  const handleNodeClick = useCallback(async (node: EntityNode) => {
    const supabase = createClient();

    // Load entity details
    const { data: entity } = await supabase
      .from("entities")
      .select("id, canonical_name, entity_type, aliases")
      .eq("id", node.id)
      .single();

    // Load linked documents
    const { data: docLinks } = await supabase
      .from("document_entities")
      .select("document_id, role")
      .eq("entity_id", node.id);

    let documents: EntityDetail["documents"] = [];
    if (docLinks && docLinks.length > 0) {
      const docIds = docLinks.map((l) => l.document_id);
      const { data: docs } = await supabase
        .from("documents")
        .select("id, original_filename")
        .in("id", docIds);

      documents = docLinks.map((link) => {
        const doc = docs?.find((d) => d.id === link.document_id);
        return {
          id: link.document_id,
          original_filename: doc?.original_filename ?? "Unknown",
          role: link.role,
        };
      });
    }

    // Load current facts
    const { data: facts } = await supabase
      .from("facts")
      .select("field_name, field_value")
      .eq("entity_id", node.id)
      .is("valid_until", null)
      .order("field_name");

    setSelectedEntity({
      id: entity?.id ?? node.id,
      canonical_name: entity?.canonical_name ?? node.canonical_name,
      entity_type: entity?.entity_type ?? node.entity_type,
      aliases: Array.isArray(entity?.aliases) ? entity.aliases : [],
      documents,
      facts: facts ?? [],
    });
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (graphData.nodes.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-center">
        <p className="text-xl font-semibold">No entities yet</p>
        <p className="mt-2 text-muted-foreground max-w-sm">
          Upload documents to start building your knowledge graph. Entities and
          relationships will appear here as documents are processed.
        </p>
      </div>
    );
  }

  return (
    <div className="relative h-full" ref={containerRef}>
      <div className="absolute top-0 left-0 z-10 p-4">
        <h2 className="text-xl font-semibold">Knowledge Graph</h2>
        <p className="text-sm text-muted-foreground">
          {graphData.nodes.length} entities, {graphData.links.length} relationships
        </p>
      </div>

      {/* Legend */}
      <div className="absolute top-0 right-0 z-10 p-4 flex gap-3">
        {Object.entries(TYPE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1 text-xs">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            <span className="capitalize">{type}</span>
          </div>
        ))}
      </div>

      <ForceGraph2D
        width={dimensions.width}
        height={dimensions.height}
        graphData={graphData}
        nodeLabel={(node) => (node as EntityNode).canonical_name}
        nodeColor={(node) => TYPE_COLORS[(node as EntityNode).entity_type] ?? TYPE_COLORS.other}
        nodeVal={(node) => Math.max(2, (node as EntityNode).doc_count * 3)}
        linkLabel={(link) => (link as unknown as RelationshipLink).relation_type.replace(/_/g, " ")}
        linkColor={() => "#d1d5db"}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={1}
        onNodeClick={(node) => handleNodeClick(node as EntityNode)}
        nodeCanvasObject={(node, ctx, globalScale) => {
          const n = node as EntityNode;
          const label = n.canonical_name;
          const fontSize = 12 / globalScale;
          ctx.font = `${fontSize}px Sans-Serif`;
          const color = TYPE_COLORS[n.entity_type] ?? TYPE_COLORS.other;
          const size = Math.max(4, (n.doc_count ?? 0) * 2 + 4);

          // Draw node circle
          ctx.beginPath();
          ctx.arc(n.x ?? 0, n.y ?? 0, size, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();

          // Draw label
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = "#374151";
          ctx.fillText(label, n.x ?? 0, (n.y ?? 0) + size + fontSize);
        }}
      />

      {/* Side Panel */}
      {selectedEntity && (
        <div className="absolute top-0 right-0 h-full w-80 bg-background border-l shadow-lg z-20 overflow-y-auto">
          <div className="p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-lg">{selectedEntity.canonical_name}</h3>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setSelectedEntity(null)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="flex items-center gap-2">
              <span
                className="rounded-full px-2 py-0.5 text-xs font-medium text-white"
                style={{
                  backgroundColor:
                    TYPE_COLORS[selectedEntity.entity_type] ?? TYPE_COLORS.other,
                }}
              >
                {selectedEntity.entity_type}
              </span>
            </div>

            {selectedEntity.aliases.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Aliases
                </p>
                <div className="flex flex-wrap gap-1">
                  {selectedEntity.aliases.map((alias, i) => (
                    <span
                      key={i}
                      className="rounded bg-accent px-2 py-0.5 text-xs"
                    >
                      {alias}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {selectedEntity.facts.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Facts
                </p>
                <div className="divide-y rounded border">
                  {selectedEntity.facts.map((fact, i) => (
                    <div key={i} className="flex justify-between p-2 text-sm">
                      <span className="text-muted-foreground">
                        {fact.field_name.replace(/_/g, " ")}
                      </span>
                      <span className="font-medium">{fact.field_value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {selectedEntity.documents.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Documents ({selectedEntity.documents.length})
                </p>
                <div className="space-y-1">
                  {selectedEntity.documents.map((doc) => (
                    <a
                      key={`${doc.id}-${doc.role}`}
                      href={`/document/${doc.id}`}
                      className="block rounded border p-2 text-sm hover:bg-accent transition-colors"
                    >
                      <p className="font-medium truncate">
                        {doc.original_filename}
                      </p>
                      <p className="text-xs text-muted-foreground">{doc.role}</p>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
