/** `repo_full_name` is always GitHub's guaranteed `owner/repo` shape (see
 * `api/routers/runs.py::RunIdentity.from_repo_full_name`) -- splitting on
 * the first `/` mirrors that backend logic exactly. */
export function splitRepoFullName(repoFullName: string): { owner: string; repo: string } {
  const slashIndex = repoFullName.indexOf("/");
  if (slashIndex === -1) {
    return { owner: repoFullName, repo: "" };
  }
  return {
    owner: repoFullName.slice(0, slashIndex),
    repo: repoFullName.slice(slashIndex + 1),
  };
}
