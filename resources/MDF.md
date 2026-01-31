# The meadow Docstring Format

_and, the [meadoc Docstring Machine](#the-meadoc-docstring-machine)_

a plaintext-first alternative documentation string style for Python

```python
class Cake(BaseModel):
    """
    a baker's confectionery, usually baked, a lie
    
    attributes:
        `name: str`
            name of the cake
        `ingredients: list[Ingredient]`
            ingredients of the cake
        `baking_duration: int`
            duration of the baking process in minutes
        `baking_temperature: int = 4000`
            temperature of the baking process in degrees kelvin
    """
    name: str
    ingredients: list[Ingredient]
    baking_duration: int
    baking_temperature: int = 4000
```

## the format

why another one? it's really just for me, but I think it's an okay-ish format

- it's easy and somewhat intuitive to read and write,
  especially because it's just plaintext

- it closely follows python syntax where it should,
  which includes type annotations

**(bonus!)** it works:

- best on Zed
- okay-ish Visual Studio Code
- eh on PyCharm

the format is comprised of multiple sections:

1. **preamble**  
    _a mandatory short one line description_

2. **body**  
    _an optional longer, potentially multi-line description_

3. **accepted (incoming) signatures**  
    _"attributes" for classes, "arguments" or "parameters" for functions_

    general format:

    ```text
    {attributes,arguments,parameters}:
        `<python variable declaration syntax>`
            <description>
    ```

4. **exported (outgoing) signatures**  
    _"functions" for module top-level docstrings, "methods" for class docstrings_

    general format:

    ```text
    {functions,methods}:
        `<python function declaration syntax without trailing colon>`
            <description of the function>
    ```

    example:

    ```text
    functions:
        `def bake(self, override: BakingOverride | None = None) -> bool`
            bakes the cake and returns True if successful
    ```

5. **returns** and **raises**

    general format, single type:

    ```text
    {returns,raises}: `<return type annotation>`
        <description>
    ```

    general format, multiple types:

    ```text
    {returns,raises}:
        `<first possible return type annotation/exception class>`
            <description>
        `<second possible return type annotation/exception class>`
            <description>
    ```

    examples:

    ```python
    def certain_unsafe_div(a: int | float, b: int | float) -> float:
        """
        divide a by b

        arguments:
            `a: int | float`
                numerator
            `b: int | float`
                denominator

        raises:
            `ZeroDivisionError`
                raised when denominator is 0
            `OverflowError`
                raised when the resulting number is too big
            `FloatingPointError`
                secret third thing

        returns: float
            the result, a divided by b
        """
        return a / b

    def uncertain_unsafe_read(path: Path) -> str:
        """
        blah blah helper blah

        arguments:
            `path: Path`
                path to read from

        raises: `Exception`
            god knows what path.read_text might raise

        returns: `str`
            the read out contents from the path
        """
        return path.read_text()
    ```

6. **usage**  
    _a markdown triple backtick block with usage examples_

    general format:

    ```markdown
    usage:
        ```python
        # ...
        ```
    ```

and are layed out as such:

1. start

    | section              | required |
    | -------------------- | -------- |
    | 1. `preamble`        | 🟢 yes   |
    | 2. `body` or `usage` | 🔴 no    |

2. details

    | section                             | required      |
    | ----------------------------------- | ------------- |
    | 3. `accepted (incoming) signatures` | 🟡 if present |
    | 4. `exported (outgoing) signatures` | 🟡 if present |
    | 5. `returns`                        | 🟡 if present |
    | 6. `raises`                         | 🟡 if present |

3. end

    | section              | required |
    | -------------------- | -------- |
    | 7. `body` or `usage` | 🔴 no    |

> **frequently questioned answers**
>
> > why do the `body` and `usage` sections appear multiple times
>
> because depending on your use case, you may have a postamble after the usage,
> or if your body is a postamble after the torso and knees section (and other
> similar use cases depending on reading flow)
>
> > what about custom text
>
> any other text will just be parsed as-is as body text, so there's no
> stopping you from adding an `example:` section (but cross-ide compatibility
> is finicky, especially with pycharm)
>
> > how does the parser detect sections
>
> the parser will only attempt compliance when matching a line with the
> following pattern:
>
> ```text
> {attributes,arguments,parameters,functions,methods,returns,raises,usage}:
> ```
>
> > what if a declaration is really long?
>
> you _could_ split the declaration into multiple lines, all within the same
> indentation level. but unless your function takes in dozens of arguments,
> a single-line declaration is preferred due to much wackier differences in
> lsp popover rendering strategies across different mainstream editors.
>
> ```text
> methods:
>     `def woah_many_argument_function(
>         ...
>     ) -> None`
>         blah blah blah blah blah blah
> ```
