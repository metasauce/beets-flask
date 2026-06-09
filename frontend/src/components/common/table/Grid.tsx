import { ComponentType } from 'react';
import { AutoSizer } from 'react-virtualized-auto-sizer';
import { List, ListProps, type RowComponentProps } from 'react-window';

export type CellComponentProps<D extends object> = RowComponentProps<D> & {
    rowIndex: number;
    colIndex: number;
};
/**
 * Props for the FixedGrid component.
 * Extends FixedSizeListProps while customizing certain properties.
 * @template D - Type of the data items in the grid
 */
export interface DynamicFlowGridProps<D extends object = object> extends Omit<
    ListProps<D>,
    'children' | 'rowCount' | 'rowHeight' | 'rowProps' | 'rowComponent'
> {
    cellHeight: number; // Height of each grid cell
    cellWidth: number; // Width of each grid cell
    cellCount: number; // Total number of cells in the grid
    cellProps: ListProps<D>['rowProps']; // Data to be passed to each cell
    cellComponent: ComponentType<CellComponentProps<D>>; // Component to render each cell
    onCellsRendered?:
        | ((
              visibleCells: { startIndex: number; stopIndex: number },
              allCells: { startIndex: number; stopIndex: number }
          ) => void)
        | undefined;
}

/**
 * A virtualized grid component that efficiently renders items in a fixed-size list layout.
 * We allow the cells to flow dynamically based on the available width.
 * @template D - Type of the data items in the grid
 */
export function DynamicFlowGrid<D extends object>({
    cellHeight,
    cellWidth,
    cellCount,
    cellProps,
    cellComponent: CellComponent,
    onCellsRendered,
    onRowsRendered,
    ...props
}: DynamicFlowGridProps<D>) {
    return (
        <AutoSizer
            id="dynamic-flow-grid-autosizer"
            renderProp={({ height, width = 0 }) => {
                // Split all album covers by row to fit width
                const colCount = Math.floor(width / cellWidth);
                const rowCount = Math.ceil(cellCount / colCount);

                return (
                    <div style={{ width, height }}>
                        <List
                            rowHeight={cellHeight}
                            rowCount={rowCount}
                            onRowsRendered={(visibleRows, allRows) => {
                                onCellsRendered?.(
                                    {
                                        startIndex:
                                            visibleRows.startIndex * colCount,
                                        stopIndex: Math.min(
                                            (visibleRows.stopIndex + 1) *
                                                colCount -
                                                1,
                                            cellCount - 1
                                        ),
                                    },
                                    {
                                        startIndex:
                                            allRows.startIndex * colCount,
                                        stopIndex: Math.min(
                                            (allRows.stopIndex + 1) * colCount -
                                                1,
                                            cellCount - 1
                                        ),
                                    }
                                );
                                onRowsRendered?.(visibleRows, allRows);
                            }}
                            rowProps={cellProps}
                            rowComponent={function CellRowWrapper({
                                index,
                                style,
                                ...props
                            }) {
                                // Calculate start and end indices for the current row
                                const startIndex = index * colCount;
                                const endIndex = Math.min(
                                    startIndex + colCount,
                                    cellCount
                                );
                                return (
                                    <div
                                        style={{
                                            ...style,
                                            overflow: 'hidden',
                                            display: 'flex',
                                            width: '100%',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                        }}
                                    >
                                        {Array.from(
                                            { length: endIndex - startIndex },
                                            (_, colIndex) => {
                                                const cellIndex =
                                                    startIndex + colIndex;
                                                return (
                                                    <CellComponent
                                                        {...(props as RowComponentProps<D>)}
                                                        key={cellIndex}
                                                        index={cellIndex}
                                                        rowIndex={index}
                                                        colIndex={colIndex}
                                                        style={{
                                                            width: cellWidth,
                                                            height: cellHeight,
                                                            boxSizing:
                                                                'border-box',
                                                            display:
                                                                'inline-block',
                                                        }}
                                                    />
                                                );
                                            }
                                        )}
                                        {
                                            // Fill with empty cells if needed to maintain layout
                                            endIndex - startIndex < colCount &&
                                                Array.from(
                                                    {
                                                        length:
                                                            colCount -
                                                            (endIndex -
                                                                startIndex),
                                                    },
                                                    (_, emptyIndex) => (
                                                        <div
                                                            key={`empty-${emptyIndex}`}
                                                            style={{
                                                                width: cellWidth,
                                                                height: cellHeight,
                                                                boxSizing:
                                                                    'border-box',
                                                                display:
                                                                    'inline-block',
                                                            }}
                                                        />
                                                    )
                                                )
                                        }
                                    </div>
                                );
                            }}
                            {...props}
                        />
                    </div>
                );
            }}
        />
    );
}
