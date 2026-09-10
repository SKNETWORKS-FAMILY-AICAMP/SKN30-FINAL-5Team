import { useState, type ReactNode } from 'react';
import {
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { colors, spacing } from '../../components/theme';
import {
  POLICY_DOCUMENTS,
  type PolicyDocumentId,
} from '../../policy_docs/documents';

type Block =
  | {
      kind: 'heading' | 'paragraph' | 'list';
      text: string;
      level?: number;
      marker?: string;
    }
  | { kind: 'table'; rows: string[][] };

// The checked-in policies use headings, paragraphs, lists, bold text and tables.
// Unrecognised syntax remains visible as text; no source content is discarded.
export function parsePolicyMarkdown(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  const cells = (line: string) =>
    line
      .trim()
      .replace(/^\||\|$/g, '')
      .split('|')
      .map((cell) => cell.trim());
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]!.trim();
    if (!line) continue;
    if (
      line.startsWith('|') &&
      /^\|?\s*:?-+:?\s*\|/.test(lines[i + 1]?.trim() ?? '')
    ) {
      const rows = [cells(line)];
      i += 2;
      while (i < lines.length && lines[i]!.trim().startsWith('|')) {
        rows.push(cells(lines[i]!));
        i += 1;
      }
      i -= 1;
      blocks.push({ kind: 'table', rows });
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({
        kind: 'heading',
        text: heading[2]!,
        level: heading[1]!.length,
      });
      continue;
    }
    const list = /^([-*+] |\d+\. )(.*)$/.exec(line);
    let body = list ? list[2]! : line;
    while (
      i + 1 < lines.length &&
      lines[i + 1]!.trim() &&
      !/^(#{1,6}\s|[-*+]\s|\d+\.\s|\|)/.test(lines[i + 1]!.trim())
    ) {
      body += ` ${lines[++i]!.trim()}`;
    }
    blocks.push(
      list
        ? { kind: 'list', text: body, marker: list[1]!.trim() }
        : { kind: 'paragraph', text: body },
    );
  }
  return blocks;
}

export function PolicyMarkdown({
  markdown,
  onLink,
}: {
  markdown: string;
  onLink: (href: string) => void;
}) {
  const inline = (text: string): ReactNode[] =>
    text.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g).map((part, index) => {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
      if (link)
        return (
          <Text
            key={index}
            accessibilityRole="link"
            onPress={() => onLink(link[2]!)}
            style={styles.link}
          >
            {link[1]}
          </Text>
        );
      if (part.startsWith('**') && part.endsWith('**'))
        return (
          <Text key={index} style={styles.bold}>
            {part.slice(2, -2)}
          </Text>
        );
      return part;
    });
  return (
    <View style={styles.document}>
      {parsePolicyMarkdown(markdown).map((block, index) => {
        if (block.kind === 'table')
          return (
            <ScrollView
              key={index}
              horizontal
              accessibilityLabel="약관 표, 가로로 스크롤하여 전체 내용 확인"
              showsHorizontalScrollIndicator
            >
              <View style={styles.table}>
                {block.rows.map((row, rowIndex) => (
                  <View
                    key={rowIndex}
                    style={[
                      styles.tableRow,
                      rowIndex === 0
                        ? styles.tableHeader
                        : rowIndex % 2 === 0 && styles.tableStripe,
                    ]}
                  >
                    {row.map((cell, column) => (
                      <View
                        key={column}
                        style={[
                          styles.cell,
                          {
                            width: row.length === 2 && column === 1 ? 310 : 205,
                          },
                        ]}
                      >
                        <Text
                          selectable
                          style={[styles.body, rowIndex === 0 && styles.bold]}
                        >
                          {inline(cell)}
                        </Text>
                      </View>
                    ))}
                  </View>
                ))}
              </View>
            </ScrollView>
          );
        return (
          <View key={index} style={block.kind === 'list' && styles.listRow}>
            {block.kind === 'list' ? (
              <Text style={styles.marker}>
                {block.marker === '-' ? '•' : block.marker}
              </Text>
            ) : null}
            <Text
              selectable
              accessibilityRole={
                block.kind === 'heading' ? 'header' : undefined
              }
              style={[
                styles.body,
                block.kind === 'list' && styles.listBody,
                block.kind === 'heading' &&
                  (block.level === 1 ? styles.title : styles.heading),
              ]}
            >
              {inline(block.text)}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

export function PolicyDetails({
  documentId,
}: {
  documentId: PolicyDocumentId;
}) {
  const [expanded, setExpanded] = useState(false);
  const [linkedId, setLinkedId] = useState<PolicyDocumentId | null>(null);
  const [linkError, setLinkError] = useState(false);
  const document = POLICY_DOCUMENTS[documentId];
  const openLink = (href: string) => {
    setLinkError(false);
    const match = (Object.keys(POLICY_DOCUMENTS) as PolicyDocumentId[]).find(
      (id) => POLICY_DOCUMENTS[id].filename === href,
    );
    if (match) {
      setLinkedId(match);
      return;
    }
    if (/^https:\/\//.test(href))
      void Linking.openURL(href).catch(() => setLinkError(true));
    else setLinkError(true);
  };
  return (
    <View style={styles.details}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${document.title} ${expanded ? '접기' : '펼쳐보기'}`}
        accessibilityState={{ expanded }}
        onPress={() => setExpanded((value) => !value)}
        style={styles.toggle}
      >
        <Text style={styles.toggleLabel}>{expanded ? '접기' : '펼쳐보기'}</Text>
        <Text style={styles.toggleLabel}>{expanded ? '⌃' : '⌄'}</Text>
      </Pressable>
      {expanded ? (
        <View testID={`policy-${documentId}`} style={styles.expanded}>
          <PolicyMarkdown markdown={document.markdown} onLink={openLink} />
          {linkedId ? (
            <View style={styles.linked}>
              <Pressable
                accessibilityRole="button"
                onPress={() => setLinkedId(null)}
                style={styles.toggle}
              >
                <Text style={styles.toggleLabel}>연결된 약관 닫기</Text>
              </Pressable>
              <PolicyMarkdown
                markdown={POLICY_DOCUMENTS[linkedId].markdown}
                onLink={openLink}
              />
            </View>
          ) : null}
          {linkError ? (
            <Text accessibilityRole="alert" style={styles.error}>
              링크를 열지 못했어요. 다시 눌러주세요.
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  details: { minWidth: 0 },
  toggle: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: spacing.sm,
    paddingHorizontal: 8,
  },
  toggleLabel: { color: colors.textSub, fontSize: 13, fontWeight: '600' },
  expanded: {
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  document: { gap: 12 },
  body: { color: colors.text, fontSize: 13, lineHeight: 21 },
  title: { fontSize: 19, lineHeight: 28, fontWeight: '700', marginBottom: 4 },
  heading: { fontSize: 15, lineHeight: 23, fontWeight: '700', marginTop: 12 },
  bold: { fontWeight: '700' },
  listRow: { flexDirection: 'row', gap: 8 },
  listBody: { flex: 1 },
  marker: { minWidth: 18, color: colors.text, fontSize: 13, lineHeight: 21 },
  table: { borderTopWidth: 1, borderLeftWidth: 1, borderColor: colors.border },
  tableRow: { flexDirection: 'row', alignItems: 'stretch' },
  tableHeader: { backgroundColor: '#EDE8DF' },
  tableStripe: { backgroundColor: '#FAF8F4' },
  cell: {
    padding: 12,
    borderRightWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.border,
  },
  link: { color: '#6B4E1F', textDecorationLine: 'underline' },
  linked: {
    marginTop: 16,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  error: { color: colors.fieldError, fontSize: 13, marginTop: 8 },
});
